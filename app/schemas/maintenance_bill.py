from sqlmodel import SQLModel, Field
from enum import Enum
from typing import List
from uuid import UUID
from datetime import datetime

from app.models.house import House

class MaintenanceStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN PROGRESS"
    COMPLETED = "COMPLETED"

class MaintenanceBillBase(SQLModel):
    hse_id: UUID = Field(foreign_key="house.id", index=True)
    title: str
    description: str | None
    labor_cost: float | None = None
    parts_cost: float | None = None
    total_amount: float | None = None
    
    status: MaintenanceStatus = Field(default=MaintenanceStatus.PENDING)
    
    date_raised: datetime | None = Field(default_factory=datetime.now)
    
class MaintenanceBillRead(MaintenanceBillBase):
    id: UUID
    
    house: House | None = None
    # tenant: Tenant | None = None
    
class EditMaintenanceStatus(SQLModel):
    status: MaintenanceStatus | None = None
    
class MaintenanceBillUpdate(SQLModel):
    labor_cost: float | None = None
    parts_cost: float | None = None