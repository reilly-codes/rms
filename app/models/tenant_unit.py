from sqlmodel import Field, Relationship
from uuid import uuid4, UUID
from typing import List, TYPE_CHECKING
from datetime import datetime

from app.schemas.tenant_unit import TenantUnitBase
if TYPE_CHECKING:
    from app.models.house import House
    from app.models.tenant import Tenant
    from app.models.invoice import Invoice

class TenantUnit(TenantUnitBase, table=True):
    __tablename__ = "tenant_unit"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    date_created: datetime = Field(default_factory=datetime.now)
    
    house: "House" = Relationship(back_populates="houses")
    tenant: "Tenant" = Relationship(back_populates="tenants")
    invoices: List["Invoice"] = Relationship(back_populates="tenant_unit")
