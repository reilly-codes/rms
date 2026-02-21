from sqlmodel import Field, Relationship
from uuid import UUID, uuid4
from datetime import datetime
from typing import List, TYPE_CHECKING

from app.schemas.property import PropertyBase
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.house import House

class Property(PropertyBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    landlord_id: UUID = Field(foreign_key="user.id")

    landlord: "User" = Relationship(back_populates="properties")
    houses: List["House"] = Relationship(back_populates="property")