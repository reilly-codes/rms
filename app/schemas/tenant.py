from sqlmodel import Field
from enum import Enum
from uuid import UUID
from typing import List
from pydantic import ConfigDict

from app.schemas.user import UserBase
from app.schemas.tenant_unit import TenantUnitRead

class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MOVING_OUT = "MOVING OUT"
    VACATED = "VACATED"

class TenantBase(UserBase):
    national_id: str | None = Field(unique=True, index=True, nullable=True)
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, index=True)
    
class TenantRead(TenantBase):
    id: UUID
    wallet_balance: float
    houses: List[TenantUnitRead] = []
    
class TenantPrint(TenantBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    wallet_balance: float
    houses: List[TenantUnitRead] = []
    
class TenantCreate(TenantBase):
    hse: UUID