from sqlmodel import SQLModel, Field
from uuid import UUID
from enum import Enum
from datetime import datetime
from typing import List

from app.schemas.utility import UtilityBillBase
from app.models.house import House
from app.models.tenant import Tenant
from app.models.utility import UtilityBill

class InvoiceStatus(str, Enum):
    PAID = "PAID"
    UNPAID = "UNPAID"

class InvoiceBase(SQLModel):
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    hse_id: UUID = Field(foreign_key="house.id", index=True)
    rent_amount: float | None
    amount: float | None
    status: InvoiceStatus = Field(default=InvoiceStatus.UNPAID, index=True)
    date_of_gen: datetime = Field(default_factory=datetime.now)
    date_due: datetime
    
class InvoiceGenerationRequest(SQLModel):
    utilities: List[UtilityBillBase]
    
class InvoiceRead(InvoiceBase):
    id: UUID
    comments: str | None
    
    house: House | None = None
    tenant: Tenant | None = None
    utilities: List[UtilityBill] = []