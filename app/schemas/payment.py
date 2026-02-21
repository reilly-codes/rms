from sqlmodel import SQLModel, Field, Relationship
from enum import Enum
from uuid import  UUID

class PaymentStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIIED = "VERIFIED"
    
class PaymentBase(SQLModel):
    invoice_id: UUID | None = Field(foreign_key="invoice.id", index=True, default=None)
    tenant_id: UUID | None = Field(foreign_key="tenant.id", index=True)
    amount_paid: float
    transaction_ref: str = Field(index=True)
    status: PaymentStatus = Field(default=PaymentStatus.UNVERIFIED, index=True)
    created_by: UUID| None = Field(foreign_key="user.id", default=None)