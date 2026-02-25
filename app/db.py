import os

from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from typing import Annotated
from sqlmodel import (
    Session,
    SQLModel,
    create_engine,
    select,
)

from app.models.role import Role

load_dotenv()

connect_args = {"check_same_thread" : False}

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True)

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
    # create_db_and_tables()
    seed_roles()
    yield
