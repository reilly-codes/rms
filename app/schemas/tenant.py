from sqlmodel import Field
from enum import Enum
from uuid import UUID
from typing import List

from app.schemas.user import UserBase
from app.schemas.tenant_unit import TenantUnitRead

class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MOVING_OUT = "MOVING OUT"
    VACATED = "VACATED"

class TenantBase(UserBase):
    national_id: str = Field(unique=True, index=True)
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, index=True)
    
class TenantRead(TenantBase):
    id: UUID
    wallet_balance: float
    houses: List[TenantUnitRead] = []