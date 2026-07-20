from sqlmodel import SQLModel, Field
from uuid import UUID
from datetime import datetime

class PropertyAssignmentBase(SQLModel):
    user_id: UUID = Field(foreign_key="user.id", index=True)   # the Caretaker or Property Manager
    property_id: UUID = Field(foreign_key="property.id", index=True)

class PropertyAssignmentCreate(SQLModel):
    user_id: UUID       # existing Caretaker/Property Manager user id
    property_id: UUID

class PropertyAssignmentCreateByEmail(SQLModel):
    """Convenience for granting an *existing* Property Manager (who may have
    been created by a different landlord) access to one of your properties —
    this is how multi-landlord access for property management companies
    actually gets wired up."""
    email: str
    property_id: UUID

class PropertyAssignmentRead(PropertyAssignmentBase):
    id: UUID
    assigned_by_id: UUID
    created_at: datetime
    revoked_at: datetime | None = None
