"""
Central "can this user touch this property?" check.

Replaces the old, never-actually-working `Property.caretaker_id` field that
app/routers/payments.py was referencing (that column doesn't exist on the
Property model, so that summary endpoint would have thrown an
AttributeError/DB error for any caretaker who hit it). Caretaker and
Property Manager access is now driven entirely by PropertyAssignment rows.
"""
from uuid import UUID
from typing import List
from sqlmodel import Session, select
from fastapi import HTTPException, status

from app.models.user import User
from app.models.property import Property
from app.models.property_assignment import PropertyAssignment


def get_accessible_property_ids(session: Session, user: User) -> List[UUID]:
    """Returns every property_id this user (landlord, caretaker, or property
    manager) is allowed to operate on."""
    if user.role_id == 1:  # Landlord
        rows = session.exec(
            select(Property.id).where(Property.landlord_id == user.id)
        ).all()
        return list(rows)

    if user.role_id in (2, 4):  # Caretaker or Property Manager
        rows = session.exec(
            select(PropertyAssignment.property_id)
            .where(PropertyAssignment.user_id == user.id)
            .where(PropertyAssignment.revoked_at == None)  # noqa: E711
        ).all()
        return list(rows)

    return []


def verify_property_access(session: Session, user: User, property_id: UUID) -> Property:
    """Raises 404 (not 403 — don't reveal existence of properties a user
    can't see) if the user has no access to this property. Returns the
    Property row on success."""
    property_obj = session.get(Property, property_id)
    if not property_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    if user.role_id == 1:
        if property_obj.landlord_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
        return property_obj

    if user.role_id in (2, 4):
        assignment = session.exec(
            select(PropertyAssignment)
            .where(PropertyAssignment.property_id == property_id)
            .where(PropertyAssignment.user_id == user.id)
            .where(PropertyAssignment.revoked_at == None)  # noqa: E711
        ).first()
        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
        return property_obj

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this resource")
