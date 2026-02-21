from sqlmodel import Field, Relationship
from uuid import uuid4, UUID
from typing import TYPE_CHECKING

from app.schemas.maintenance_bill import MaintenanceBillBase
if TYPE_CHECKING:
    from app.models.house import House

class MaintenanceBill(MaintenanceBillBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    
    house: "House" = Relationship()