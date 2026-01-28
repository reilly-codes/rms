from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from typing import Annotated
from sqlmodel import (
    Session,
    SQLModel,
    create_engine,
    select,
)

from models import Role

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread" : False}
engine = create_engine(sqlite_url, connect_args=connect_args)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def seed_roles():
    with Session(engine) as session:
        existing_role = session.exec(select(Role)).first()

        if not existing_role:
            print("seeding roles...")
            landlord = Role(id=1, name="Landlord", description="Property owner and Admin")
            tenant = Role(id=2, name="Tenant", description="Rents a property unit")

            session.add(landlord)
            session.add(tenant)
            session.commit()

            print("Roles successfully seeded")

        else:
            print("Roles already exist. Skipping seed")

def get_session():
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    seed_roles()
    yield
