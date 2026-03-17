from sqlmodel import SQLModel, Field
from uuid import UUID
from enum import Enum
from datetime import datetime
from typing import List

from app.schemas.utility import UtilityBillBase, UtilityBillRead
from app.schemas.tenant_unit import TenantUnitRead

class InvoiceStatus(str, Enum):
    PAID = "PAID"
    UNPAID = "UNPAID"

class InvoiceBase(SQLModel):
    tenant_unit_id: UUID = Field(foreign_key="tenant_unit.id")
    rent_amount: float | None
    amount: float | None
    status: InvoiceStatus = Field(default=InvoiceStatus.UNPAID, index=True)
    date_of_gen: datetime = Field(default_factory=datetime.now)
    date_due: datetime
    updated_at: datetime | None = None
    
class InvoiceGenerationRequest(SQLModel):
    utilities: List[UtilityBillBase]
    
class InvoiceRead(InvoiceBase):
    id: UUID
    comments: str | None
    
    tenant_unit: TenantUnitRead | None = None
    utilities: List[UtilityBillRead] = []