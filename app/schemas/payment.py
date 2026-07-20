# app/schemas/payment.py
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from app.models.payment import PaymentStatus

class PaymentBase(BaseModel):
    invoice_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    amount_paid: float
    transaction_ref: str
    status: PaymentStatus = PaymentStatus.UNVERIFIED
    date_paid: datetime

class PaymentEditSchema(BaseModel):
    amount_paid: Optional[float] = None
    transaction_ref: Optional[str] = None
    status: Optional[PaymentStatus] = None
    date_paid: Optional[datetime] = None

# Unified Payment Response containing the allocation breakdown
class PaymentResponse(BaseModel):
    id: UUID
    invoice_id: Optional[UUID]
    tenant_id: Optional[UUID]
    amount_paid: float
    rent_allocated: float
    utilities_allocated: float
    transaction_ref: str
    status: PaymentStatus
    date_paid: datetime
    created_at: datetime

# Schema for Property-specific breakdown summary
class PropertyPaymentSummary(BaseModel):
    property_id: UUID
    property_name: str
    total_rent_collected: float
    total_utilities_collected: float
    total_collected: float
    payments: List[PaymentResponse]

# Schema for the complete dashboard overview
class LandlordDashboardSummary(BaseModel):
    grand_total_rent: float
    grand_total_utilities: float
    grand_total_collected: float
    by_property: List[PropertyPaymentSummary]