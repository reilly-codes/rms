from sqlmodel import SQLModel, Field
from uuid import UUID
from datetime import datetime

class TenantUnitBase(SQLModel):
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    hse_id: UUID = Field(foreign_key="house.id", index=True)
    rent_begin: datetime
    rent_end: datetime
    
class TenantUnitRead(TenantUnitBase):
    id: UUID
    date_created: datetime