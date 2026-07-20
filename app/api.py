# app/api.py
from typing import Annotated, List
from fastapi import APIRouter, Depends
from sqlmodel import select

# Database dependencies
from app.core.database import SessionDep

# Router module imports
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
    reconciliation,
    subscriptions,
    property_assignments,
    expenses,
    mpesa,
)
from app.services.auth_service import get_current_active_user
from app.models.user import User
from app.models.house import House
from app.models.property import Property

# Create a master API router
api_router = APIRouter()

# 1. Include Routers cleanly
api_router.include_router(tokens.router)
api_router.include_router(users.router)
api_router.include_router(properties.router)
api_router.include_router(houses.router)
api_router.include_router(tenants.router)
api_router.include_router(invoices.router) 
api_router.include_router(payments.router) 
api_router.include_router(transactions.router)
api_router.include_router(reconciliation.router)
api_router.include_router(maintenance_bills.router)
api_router.include_router(broadcast.router)  
api_router.include_router(subscriptions.router)
api_router.include_router(property_assignments.router)
api_router.include_router(expenses.router)
api_router.include_router(mpesa.router)

# 2. Refactored global/cross-resource endpoints
@api_router.get("/landlords/units/all", response_model=List[House], tags=["Properties"])
async def get_all_landlord_units(
    session: SessionDep, 
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    statement = (
        select(House)
        .join(Property, House.property_id == Property.id)
        .where(Property.landlord_id == current_user.id)
    )
    units = session.exec(statement).all()
    return units

@api_router.get("/alive", tags=["Health"])
async def stay_alive():
    return {"status": "alive"}