from sqlmodel import Field, Relationship
from uuid import UUID, uuid4
from datetime import datetime
from typing import List, TYPE_CHECKING


from app.schemas.user import UserBase
if TYPE_CHECKING:
    from app.models.property import Property

class User(UserBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hashed_password: str
    disabled: bool = False
    created_at: datetime = Field(default_factory=datetime.now)

    properties: List["Property"] = Relationship(back_populates="landlord")
