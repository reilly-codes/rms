from sqlmodel import Field, Relationship
from uuid import UUID, uuid4
from datetime import datetime
from typing import TYPE_CHECKING

from app.schemas.expense import ExpenseBase
if TYPE_CHECKING:
    from app.models.property import Property
    from app.models.house import House

class Expense(ExpenseBase, table=True):
    """
    An outgoing cost against a property (or a specific unit within it),
    raised by a Landlord, Caretaker, or Property Manager. Can be logged as
    already PAID (with an optional receipt photo and/or pasted M-Pesa
    confirmation message) or as OUTSTANDING, to be marked paid later via
    PATCH /expenses/{id}.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    landlord_id: UUID = Field(foreign_key="user.id", index=True)  # denormalized for fast scoping/summaries
    created_by: UUID = Field(foreign_key="user.id")  # who actually logged it (landlord/caretaker/PM)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None

    property: "Property" = Relationship()
    house: "House" = Relationship()
