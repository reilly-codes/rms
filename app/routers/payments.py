# app/routers/payments.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from typing import List, Annotated
from uuid import UUID
from datetime import datetime

from app.core.database import SessionDep
from app.core.roles import require_management, require_tenant
from app.services.auth_service import get_current_active_user

from app.models.payment import Payment
from app.models.house import House
from app.models.tenant_unit import TenantUnit
from app.models.property import Property
from app.models.invoice import Invoice
from app.models.user import User

from app.schemas.payment import (
    PaymentBase, 
    PaymentEditSchema,
    PaymentResponse,
    LandlordDashboardSummary,
    PropertyPaymentSummary
)
from app.services.payment_service import PaymentService
from app.services.access_control import get_accessible_property_ids

router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
    dependencies=[Depends(get_current_active_user)]
)


@router.post("/process/payment", response_model=PaymentResponse)
async def create_payment(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    new_payment: PaymentBase
):
    """Register payment, logging explicit date paid, reference code, and breakdown allocation."""
    return PaymentService.process_new_payment(session, new_payment, current_user.id)


@router.get("/me", response_model=List[dict])
async def get_tenant_payments(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_tenant)],
):
    """Retrieve current logged-in tenant's invoices along with detailed payment breakdowns."""
    from app.models.tenant import Tenant
    
    tenant = session.exec(select(Tenant).where(Tenant.user_id == current_user.id)).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant profile not found")
    
    invoices = session.exec(
        select(Invoice)
        .join(TenantUnit, Invoice.tenant_unit_id == TenantUnit.id)
        .where(TenantUnit.tenant_id == tenant.id)
        .order_by(Invoice.date_due.desc())
    ).all()
    
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
                    "id": str(p.id),
                    "amount": p.amount_paid,
                    "rent_allocated": p.rent_allocated,
                    "utilities_allocated": p.utilities_allocated,
                    "date": p.date_paid.isoformat(),
                    "ref": p.transaction_ref,
                    "status": p.status.value,
                }
                for p in invoice.payments
            ]
        })
    
    return result


@router.get("/summary", response_model=LandlordDashboardSummary)
async def get_payments_dashboard_summary(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_management)],
    date_from: datetime | None = None,
    date_to: datetime | None = None
):
    """
    Retrieve structured financial summaries broken down per property, 
    including a grand total of all collections. Caretakers only see their assigned properties.
    """
    from app.core.roles import ROLE_MAP
    user_role_name = ROLE_MAP.get(current_user.role_id, "")
    
    # 1. Fetch properties based on role assignment rules.
    # BUGFIX: this used to filter on `Property.caretaker_id`, a column that
    # never existed on the Property model — any caretaker hitting this
    # endpoint would have gotten a hard DB error. Caretaker/Property
    # Manager scoping is now driven by PropertyAssignment rows instead.
    if user_role_name == "landlord":
        prop_statement = select(Property).where(Property.landlord_id == current_user.id)
        properties = session.exec(prop_statement).all()
    elif user_role_name in ("caretaker", "propertymanager"):
        accessible_ids = get_accessible_property_ids(session, current_user)
        properties = session.exec(select(Property).where(Property.id.in_(accessible_ids))).all() if accessible_ids else []
    else:
        properties = []
    
    by_property_list = []
    grand_total_rent = 0.0
    grand_total_utilities = 0.0
    grand_total_collected = 0.0
    
    # 2. Iterate properties to compute their respective payment allocations
    for prop in properties:
        # Fetch all payments belonging to this property's houses
        payment_statement = (
            select(Payment)
            .join(TenantUnit, Payment.tenant_id == TenantUnit.tenant_id)
            .join(House, TenantUnit.hse_id == House.id)
            .where(House.property_id == prop.id)
        )
        
        # Apply optional date filters based on transaction payment date
        if date_from:
            payment_statement = payment_statement.where(Payment.date_paid >= date_from)
        if date_to:
            payment_statement = payment_statement.where(Payment.date_paid <= date_to)
            
        payments = session.exec(payment_statement).unique().all()
        
        prop_rent = sum(p.rent_allocated for p in payments)
        prop_utils = sum(p.utilities_allocated for p in payments)
        prop_total = sum(p.amount_paid for p in payments)
        
        by_property_list.append(
            PropertyPaymentSummary(
                property_id=prop.id,
                property_name=prop.name,
                total_rent_collected=prop_rent,
                total_utilities_collected=prop_utils,
                total_collected=prop_total,
                payments=payments
            )
        )
        
        # Accumulate overall aggregates
        grand_total_rent += prop_rent
        grand_total_utilities += prop_utils
        grand_total_collected += prop_total

    return LandlordDashboardSummary(
        grand_total_rent=grand_total_rent,
        grand_total_utilities=grand_total_utilities,
        grand_total_collected=grand_total_collected,
        by_property=by_property_list
    )


@router.patch("/edit/payment/{payment_id}", response_model=PaymentResponse)
async def edit_payment(
    session: SessionDep,
    payment_id: UUID,
    payment: PaymentEditSchema,
    current_user: Annotated[User, Depends(require_management)]
):
    """Modify payment metadata details (Scoped strictly to landlords or property caretakers)."""
    existing_payment = session.get(Payment, payment_id)
    
    if not existing_payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment could not be found")
    
    # Optional Security: Ensure caretaker/landlord editing has authorization over the payment's unit
    pm = payment.model_dump(exclude_unset=True)
    
    for key, value in pm.items():
        setattr(existing_payment, key, value)
        
    session.add(existing_payment)
    session.commit()
    session.refresh(existing_payment)
    
    return existing_payment