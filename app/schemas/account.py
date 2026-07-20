from sqlmodel import SQLModel, Field
from enum import Enum
from uuid import UUID
from datetime import datetime

class AccountType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"                          # a single landlord managing their own properties
    PROPERTY_MANAGEMENT_COMPANY = "PROPERTY_MANAGEMENT_COMPANY"  # unlocks the Property Manager role

class AccountBase(SQLModel):
    business_name: str | None = None
    account_type: AccountType = Field(default=AccountType.INDIVIDUAL, index=True)

class AccountRead(AccountBase):
    id: UUID
    landlord_id: UUID
    status: str
    created_at: datetime

class AccountUpdate(SQLModel):
    business_name: str | None = None
    account_type: AccountType | None = None
