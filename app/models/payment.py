# app/models/payment.py
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from uuid import uuid4, UUID
from typing import Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.transaction import Transaction

class PaymentStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"

class PaymentBase(SQLModel):
    invoice_id: UUID | None = Field(foreign_key="invoice.id", index=True, default=None)
    tenant_id: UUID | None = Field(foreign_key="tenant.id", index=True, default=None)
    amount_paid: float
    transaction_ref: str = Field(index=True)
    status: PaymentStatus = Field(default=PaymentStatus.UNVERIFIED, index=True)
    created_by: UUID | None = Field(foreign_key="user.id", default=None)
    
    # NEW FIELDS: Crucial for tracking the exact payment day and internal division
    date_paid: datetime = Field(default_factory=datetime.now)  
    rent_allocated: float = Field(default=0.0)      
    utilities_allocated: float = Field(default=0.0) 

class Payment(PaymentBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    transaction_id: UUID | None = Field(foreign_key="transaction.id", index=True, default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None

    invoice: Optional["Invoice"] = Relationship(back_populates="payments")
    transaction: Optional["Transaction"] = Relationship(
        back_populates="payments",
        sa_relationship_kwargs={"foreign_keys": "Payment.transaction_id"},
    )