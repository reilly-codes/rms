from sqlmodel import Field, Relationship
from uuid import UUID, uuid4
from datetime import datetime
from typing import TYPE_CHECKING

from app.schemas.property_assignment import PropertyAssignmentBase
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.property import Property

class PropertyAssignment(PropertyAssignmentBase, table=True):
    """
    Grants a Caretaker or Property Manager (user_id) access to a specific
    Property. This is what replaces the old (never-implemented)
    Property.caretaker_id column, and it's the mechanism that lets a
    Property Manager end up with access to properties owned by several
    different landlords: each landlord who wants to use that PM just creates
    their own PropertyAssignment row pointing at their property.

    Assignments are soft-revoked (revoked_at set) rather than deleted, so
    access history survives even after a caretaker is reassigned elsewhere.
    """
    __tablename__ = "property_assignment"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    assigned_by_id: UUID = Field(foreign_key="user.id")  # the landlord who granted this
    created_at: datetime = Field(default_factory=datetime.now)
    revoked_at: datetime | None = None

    user: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "PropertyAssignment.user_id"}
    )
    property: "Property" = Relationship()
