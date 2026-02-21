from sqlmodel import Field, Relationship
from uuid import UUID, uuid4
from datetime import datetime
from typing import List, TYPE_CHECKING

from app.schemas.house import HouseBase
if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.tenant import Tenant

class House(HouseBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    property_id: UUID = Field(foreign_key="property.id")

    property: "Property" = Relationship(back_populates="houses")
    tenants: List["Tenant"] = Relationship(back_populates="house")