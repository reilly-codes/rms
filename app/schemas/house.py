from sqlmodel import SQLModel, Field
from enum import Enum
from uuid import UUID
from typing import List

from app.schemas.tenant_unit import TenantUnitRead

class HouseStatus(str, Enum):
    VACANT = "VACANT"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"

class HouseBase(SQLModel):
    number: str = Field(index=True)
    rent: float
    deposit: float
    description: str
    status: HouseStatus = Field(default=HouseStatus.VACANT, index=True)
    
class HouseRead(HouseBase):
    id: UUID
    tenants: List[TenantUnitRead] = []