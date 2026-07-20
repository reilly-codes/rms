from sqlmodel import SQLModel, Field
from enum import Enum
from uuid import UUID
from datetime import datetime

class ExpenseCategory(str, Enum):
    MAINTENANCE = "MAINTENANCE"
    UTILITIES = "UTILITIES"
    SECURITY = "SECURITY"
    CLEANING = "CLEANING"
    STAFF_SALARY = "STAFF_SALARY"
    LEGAL = "LEGAL"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"

class ExpenseStatus(str, Enum):
    PAID = "PAID"
    OUTSTANDING = "OUTSTANDING"

class ExpensePaymentMethod(str, Enum):
    MPESA = "MPESA"
    BANK = "BANK"
    CASH = "CASH"
    OTHER = "OTHER"

class ExpenseBase(SQLModel):
    property_id: UUID = Field(foreign_key="property.id", index=True)
    house_id: UUID | None = Field(foreign_key="house.id", default=None, index=True)
    category: ExpenseCategory = Field(default=ExpenseCategory.OTHER, index=True)
    description: str  # narration: what the expense was for
    amount: float
    status: ExpenseStatus = Field(default=ExpenseStatus.OUTSTANDING, index=True)
    payment_method: ExpensePaymentMethod | None = None
    date_incurred: datetime = Field(default_factory=datetime.now)
    date_paid: datetime | None = None
    mpesa_message: str | None = None   # raw pasted confirmation SMS, optional
    mpesa_code: str | None = Field(default=None, index=True)  # parsed from mpesa_message if not given
    receipt_photo_path: str | None = None

class ExpenseRead(ExpenseBase):
    id: UUID
    landlord_id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None = None

class ExpenseUpdate(SQLModel):
    house_id: UUID | None = None
    category: ExpenseCategory | None = None
    description: str | None = None
    amount: float | None = None
    status: ExpenseStatus | None = None
    payment_method: ExpensePaymentMethod | None = None
    date_paid: datetime | None = None
    mpesa_message: str | None = None
    mpesa_code: str | None = None

class ExpenseSummaryByCategory(SQLModel):
    category: ExpenseCategory
    total: float
    paid: float
    outstanding: float

class ExpenseSummary(SQLModel):
    property_id: UUID
    total_expenses: float
    total_paid: float
    total_outstanding: float
    by_category: list[ExpenseSummaryByCategory]
