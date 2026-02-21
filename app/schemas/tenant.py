from sqlmodel import Field
from enum import Enum
from uuid import UUID

from app.schemas.user import UserBase

class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MOVING_OUT = "MOVING OUT"
    VACATED = "VACATED"

class TenantBase(UserBase):
    national_id: str = Field(unique=True, index=True)
    hse: UUID = Field(foreign_key="house.id")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, index=True)