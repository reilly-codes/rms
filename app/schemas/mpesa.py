from sqlmodel import SQLModel, Field
from enum import Enum
from uuid import UUID
from datetime import datetime

class MpesaPurpose(str, Enum):
    RENT = "RENT"                # tenant paying an invoice
    SUBSCRIPTION = "SUBSCRIPTION"  # landlord paying their RMS subscription

class MpesaRequestStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class MpesaSTKRequestBase(SQLModel):
    purpose: MpesaPurpose
    phone_number: str
    amount: float
    invoice_id: UUID | None = Field(foreign_key="invoice.id", default=None, index=True)
    account_id: UUID | None = Field(foreign_key="account.id", default=None, index=True)
    initiated_by: UUID = Field(foreign_key="user.id")

class STKPushInitiateRent(SQLModel):
    invoice_id: UUID
    phone_number: str
    amount: float

class STKPushInitiateSubscription(SQLModel):
    phone_number: str
    amount: float

class MpesaSTKRequestRead(MpesaSTKRequestBase):
    id: UUID
    checkout_request_id: str | None = None
    merchant_request_id: str | None = None
    status: MpesaRequestStatus
    result_desc: str | None = None
    mpesa_receipt: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
