# app/core/database.py
import os
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from sqlmodel import (
    Session,
    SQLModel,
    create_engine,
)

# 1. Safely load env variables with override support
load_dotenv()  # Load default root .env first
env_mode = os.getenv("ENVIRONMENT", "development")

if env_mode == "production":
    load_dotenv(".env.production", override=True)
else:
    load_dotenv(".env.development", override=True)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("🚨 DATABASE_URL is missing! Check your .env file.")

# 2. Only apply check_same_thread if we are running SQLite
engine_kwargs = {"echo": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)


def create_db_and_tables():
    # BUGFIX: Role must be imported before metadata.create_all() runs —
    # SQLAlchemy resolves every FK's referenced table while sorting DDL,
    # and User.role_id -> role.id can't resolve unless the Role class has
    # actually been evaluated somewhere first. Nothing else in the app
    # imports app.models.role at module load time, so this was crashing
    # with NoReferencedTableError on any DB where Alembic hadn't already
    # created every table beforehand (i.e. any genuinely fresh DB).
    from app.models.role import Role  # noqa: F401
    SQLModel.metadata.create_all(engine)


def seed_roles():
    # Import Role inline here to prevent circular imports as models grow!
    from app.models.role import Role

    with Session(engine) as session:
        roles = [
            Role(id=1, name="Landlord", description="Property owner and Admin"),
            # SWAPPED: Caretaker is now ID 2
            Role(id=2, name="Caretaker", description="Manages a single property on behalf of a landlord"),
            # SWAPPED: Tenant is now ID 3
            Role(id=3, name="Tenant", description="Rents a property unit"),
            Role(id=4, name="Property Manager", description="Manages properties across one or more landlords (property management companies)"),
        ]
        for role in roles:
            existing = session.get(Role, role.id)
            if not existing:
                session.add(role)
        session.commit()            


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist before running seeds (if not using Alembic migrations)
    create_db_and_tables() 
    seed_roles()
    yield