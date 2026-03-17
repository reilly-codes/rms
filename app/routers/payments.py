from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from typing import List, Annotated
from uuid import UUID
from datetime import datetime

from app.db import SessionDep
from app.models.payment import Payment
from app.models.house import House
from app.models.tenant_unit import TenantUnit
from app.models.property import Property
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.payment import PaymentBase
from app.routers.users import active_user

router = APIRouter(
    tags=["Payments"],
    dependencies=[Depends(active_user)]
)

# @router.get("/payments/all", response_model=List[Payment])
# async def get_all_payments(
#     session: SessionDep,
#     current_user: Annotated[User, Depends(active_user)],
#     hse_id: UUID | None = None,
#     tenant_id: UUID | None = None,
#     date_from: datetime | None = None,
#     date_to: datetime | None = None
# ):
#     statement = select(Payment).join(Invoice, isouter=True).join(TenantUnit, Invoice.tenant_unit_id == TenantUnit.id, isouter=True)
    
#     if hse_id:
#         statement = statement.where(TenantUnit.hse_id == hse_id)
        
#     if tenant_id:
#         statement = statement.where(TenantUnit.tenant_id == tenant_id) 
        
#     statement = statement.join(House, (House.id == TenantUnit.hse_id) , isouter=True)
#     statement = statement.join(Property, Property.id == House.property_id, isouter=True)
#     statement = statement.where(Property.landlord_id == current_user.id)
    
#     if date_from:
#         statement = statement.where(Payment.created_at >= date_from)

#     if date_to:
#         statement = statement.where(Payment.created_at <= date_to)
    
#     payments = session.exec(statement).unique().all()
    
#     return payments

@router.get("/payments/all", response_model=List[Payment])
async def get_all_payments(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    hse_id: UUID | None = None,
    tenant_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None
):
    # FIX 1: Use strict Inner Joins and explicitly state the foreign keys
    statement = (
        select(Payment)
        .join(TenantUnit, Payment.tenant_id == TenantUnit.tenant_id)
        .join(House, TenantUnit.hse_id == House.id)
        .join(Property, House.property_id == Property.id)
    )
    
    # FIX 2: Security check - only return payments for this landlord's properties
    statement = statement.where(Property.landlord_id == current_user.id)
    
    # Optional Filters
    if hse_id:
        statement = statement.where(TenantUnit.hse_id == hse_id)
        
    if tenant_id:
        statement = statement.where(TenantUnit.tenant_id == tenant_id) 
    
    if date_from:
        statement = statement.where(Payment.created_at >= date_from)

    if date_to:
        statement = statement.where(Payment.created_at <= date_to)
    
    payments = session.exec(statement).unique().all()
    
    return payments

@router.post("/process/payment", response_model=Payment)
async def create_payment(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    new_payment: PaymentBase
):
    payment = new_payment.model_dump()
    payment["created_by"] = current_user.id
    
    if payment["tenant_id"]=="" and payment["invoice_id"] != "":
        qry = select(Invoice).where(Invoice.id == payment["invoice_id"])
        invoice = session.exec(qry).first()
        payment["tenant_id"] = invoice.tenant_id
         
    db_payment = Payment(**payment)
    
    session.add(db_payment)
    session.commit()
    session.refresh(db_payment)
    
    return db_payment

@router.patch("/edit/payment/{payment_id}", response_model=Payment)
async def edit_payment(
    session: SessionDep,
    payment_id: UUID,
    payment: PaymentBase
):
    existing_payment = session.get(Payment, payment_id)
    
    if not existing_payment:
        raise HTTPException(status_code=404, detail="Payment could not be found")
    
    pm = payment.model_dump(exclude_unset=True)
    
    for key, value in pm.items():
        setattr(existing_payment, key, value)
        
    session.add(existing_payment)
    session.commit()
    session.refresh(existing_payment)
    
    return existing_payment
