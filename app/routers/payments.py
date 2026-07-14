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

@router.get("/me", response_model=list)
async def get_tenant_payments(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
):
    """Get current tenant's invoice/payment history."""
    from app.models.tenant import Tenant
    from app.models.tenant_unit import TenantUnit
    from app.models.invoice import Invoice
    
    # Get tenant for this user
    tenant_stmt = select(Tenant).where(Tenant.user_id == current_user.id)
    tenant = session.exec(tenant_stmt).first()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Get all invoices for this tenant's units
    invoices_stmt = (
        select(Invoice)
        .join(TenantUnit, Invoice.tenant_unit_id == TenantUnit.id)
        .where(TenantUnit.tenant_id == tenant.id)
        .order_by(Invoice.date_due.desc())
    )
    
    invoices = session.exec(invoices_stmt).all()
    
    result = []
    for invoice in invoices:
        total_paid = sum(p.amount_paid for p in invoice.payments)
        balance = (invoice.rent_amount or 0) + (invoice.amount or 0) - total_paid
        
        result.append({
            "id": str(invoice.id),
            "date_generated": invoice.date_of_gen.isoformat(),
            "date_due": invoice.date_due.isoformat(),
            "description": f"Rent {invoice.date_due.strftime('%B %Y')}" + (f" + Utilities" if invoice.utilities else ""),
            "rent": invoice.rent_amount or 0,
            "utilities": invoice.amount or 0,
            "total_due": (invoice.rent_amount or 0) + (invoice.amount or 0),
            "total_paid": total_paid,
            "balance": balance,
            "status": invoice.status.value,
            "payments": [
                {
                    "amount": p.amount_paid,
                    "date": p.created_at.isoformat(),
                    "ref": p.transaction_ref,
                    "status": p.status.value,
                }
                for p in invoice.payments
            ]
        })
    
    return result
@router.get("/by-tenant", response_model=list)
async def get_payments_by_tenant(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    tenant_id: UUID | None = None,
):
    """Get tenant payments for landlord/caretaker."""
    from app.models.property import Property
    from app.models.house import House
    from app.models.tenant_unit import TenantUnit
    from app.models.invoice import Invoice
    
    # Build base statement
    stmt = (
        select(Invoice)
        .join(TenantUnit, Invoice.tenant_unit_id == TenantUnit.id)
        .join(House, TenantUnit.hse_id == House.id)
        .join(Property, House.property_id == Property.id)
        .order_by(Invoice.date_due.desc())
    )
    
    # Security: filter by current user's properties
    if current_user.role_id == 1:  # Landlord
        stmt = stmt.where(Property.landlord_id == current_user.id)
    elif current_user.role_id == 3:  # Caretaker
        # TODO: Add caretaker-property assignment if not already there
        pass
    
    # Optional tenant filter
    if tenant_id:
        stmt = stmt.where(TenantUnit.tenant_id == tenant_id)
    
    invoices = session.exec(stmt).all()
    
    result = []
    for invoice in invoices:
        total_paid = sum(p.amount_paid for p in invoice.payments)
        balance = (invoice.rent_amount or 0) + (invoice.amount or 0) - total_paid
        
        result.append({
            "id": str(invoice.id),
            "tenant_id": str(invoice.tenant_unit.tenant_id),
            "date_due": invoice.date_due.isoformat(),
            "rent": invoice.rent_amount or 0,
            "utilities": invoice.amount or 0,
            "total_due": (invoice.rent_amount or 0) + (invoice.amount or 0),
            "total_paid": total_paid,
            "balance": balance,
            "status": invoice.status.value,
        })
    
    return result

@router.post("/process/payment", response_model=Payment)
async def create_payment(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    new_payment: PaymentBase
):
    payment = new_payment.model_dump()
    payment["created_by"] = current_user.id
    
    if payment.get("tenant_id") is None and payment.get("invoice_id"):
        qry = select(Invoice).where(Invoice.id == payment["invoice_id"])
        invoice = session.exec(qry).first()
        if invoice:
            tu = session.get(TenantUnit, invoice.tenant_unit_id)
            if tu:
                payment["tenant_id"] = tu.tenant_id
         
    db_payment = Payment(**payment)
    
    session.add(db_payment)
    session.commit()
    session.refresh(db_payment)
    
    return db_payment    

@router.get("/payments/all", response_model=list)
async def get_all_payments(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    hse_id: UUID | None = None,
    tenant_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None
):
    """Get all payments for landlord's/caretaker's tenants."""
    from app.models.tenant import Tenant
    
    statement = (
        select(Payment)
        .join(Tenant, Payment.tenant_id == Tenant.id)
        .join(TenantUnit, Tenant.id == TenantUnit.tenant_id)
        .join(House, TenantUnit.hse_id == House.id)
        .join(Property, House.property_id == Property.id)
    )
    
    # Security: only landlord's properties
    if current_user.role_id == 1:  # Landlord
        statement = statement.where(Property.landlord_id == current_user.id)
    elif current_user.role_id == 3:  # Caretaker
        # Caretaker sees only their assigned property (if model supports it)
        # For now, assume caretaker can see all tenant payments
        pass
    
    # Optional filters
    if hse_id:
        statement = statement.where(TenantUnit.hse_id == hse_id)
    if tenant_id:
        statement = statement.where(Payment.tenant_id == tenant_id)
    if date_from:
        statement = statement.where(Payment.created_at >= date_from)
    if date_to:
        statement = statement.where(Payment.created_at <= date_to)
    
    payments = session.exec(statement).unique().all()
    
    return [
        {
            "id": str(p.id),
            "tenant_id": str(p.tenant_id),
            "amount": p.amount_paid,
            "status": p.status.value,
            "date": p.created_at.isoformat(),
            "transaction_ref": p.transaction_ref,
        }
        for p in payments
    ]


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
