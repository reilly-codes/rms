from sqlmodel import SQLModel, Field
from enum import Enum
from datetime import datetime
from uuid import UUID

class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    IGNORED = "IGNORED"

class TransactionSource(str, Enum):
    BANK = "BANK"
    MPESA = "MPESA"
    MANUAL = "MANUAL"

class TransactionBase(SQLModel):
    transaction_reference: str = Field(unique=True)
    transaction_date: datetime 
    amount: float 
    transaction_status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    # Populated when the uploaded statement includes them (most M-Pesa
    # paybill/till statements and many bank exports do). These are what
    # power auto-matching straight from a bank statement, without the
    # tenant ever having to type or paste their M-Pesa code.
    source: TransactionSource = Field(default=TransactionSource.BANK)
    # The M-Pesa "Account Number" field on paybill statements — landlords in
    # Kenya near-universally have tenants use their house/unit number as
    # the paybill account number, which makes it a far more reliable
    # auto-match key than phone number or payer name (tenants pay from
    # spouses'/relatives' phones under different names all the time).
    house_number: str | None = Field(default=None, index=True)
    phone_number: str | None = Field(default=None, index=True)
    payer_name: str | None = Field(default=None, index=True)
    raw_narrative: str | None = None
    matched_payment_id: UUID | None = Field(foreign_key="payment.id", default=None, index=True)
