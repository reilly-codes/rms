# app/routers/property_assignments.py
from fastapi import APIRouter, Depends
from typing import Annotated, List
from uuid import UUID

from app.core.database import SessionDep
from app.core.roles import require_landlord, require_management
from app.models.user import User
from app.schemas.property_assignment import (
    PropertyAssignmentCreate,
    PropertyAssignmentCreateByEmail,
    PropertyAssignmentRead,
)
from app.services.property_assignment_service import PropertyAssignmentService

router = APIRouter(
    prefix="/property-assignments",
    tags=["Property Assignments"],
)


@router.post("/", response_model=PropertyAssignmentRead)
async def assign_caretaker_or_manager(
    payload: PropertyAssignmentCreate,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    """Grant a Caretaker or Property Manager you already created access to
    one of your properties."""
    return PropertyAssignmentService.assign(session, current_landlord, payload.user_id, payload.property_id)


@router.post("/by-email", response_model=PropertyAssignmentRead)
async def assign_property_manager_by_email(
    payload: PropertyAssignmentCreateByEmail,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    """Grant an *existing* Property Manager — even one another landlord
    created — access to one of your properties. This is the multi-landlord
    entry point for property management companies."""
    return PropertyAssignmentService.assign_property_manager_by_email(
        session, current_landlord, payload.email, payload.property_id
    )


@router.get("/mine", response_model=List[PropertyAssignmentRead])
async def list_my_assignments(
    current_user: Annotated[User, Depends(require_management)],
    session: SessionDep,
):
    """A Caretaker or Property Manager viewing every property they currently
    have access to (Property Managers may see properties from several
    different landlords here). Landlords see assignments they've granted."""
    if current_user.role_id == 1:
        return PropertyAssignmentService.list_for_landlord(session, current_user)
    return PropertyAssignmentService.list_for_user(session, current_user.id)


@router.delete("/{assignment_id}")
async def revoke_assignment(
    assignment_id: UUID,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    PropertyAssignmentService.revoke(session, current_landlord, assignment_id)
    return {"message": "Assignment revoked"}
