from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List
from sqlmodel import select

from app.models.house import House
from app.models.property import Property
from app.models.user import User
from app.db import SessionDep, lifespan
from app.routers import (
    tokens,
    users,
    properties,
    houses,
    tenants,
    invoices,
    transactions,
    payments,
    maintenance_bills,
    broadcast,
    reconciliation
)
from app.routers.users import active_user

app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "https://rentmgt.netlify.app",
    "https://rms-ii8e.onrender.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,   
    allow_credentials=True,  
    allow_methods=["*"],     
    allow_headers=["*"],     
)

app.include_router(tokens.router)
app.include_router(users.router)
app.include_router(properties.router)
app.include_router(houses.router)
app.include_router(tenants.router)
app.include_router(invoices.router) 
app.include_router(payments.router) 
app.include_router(transactions.router)
app.include_router(reconciliation.router)
app.include_router(maintenance_bills.router)
app.include_router(broadcast.router)  
@app.get("/landlords/units/all", response_model=List[House])
async def get_all_landlord_units(session: SessionDep, current_user: Annotated[User, Depends(active_user)]):
    statement = (
        select(House)
        .join(Property, House.property_id == Property.id)
        .where(Property.landlord_id == current_user.id)
    )
    units = session.exec(statement).all()
    return units

    

# handle tenant wallet balance
