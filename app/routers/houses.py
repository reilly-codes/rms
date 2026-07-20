# app/routers/houses.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from typing import List, Annotated
from uuid import UUID

from app.core.database import SessionDep
from app.models.property import Property
from app.models.house import House
from app.models.user import User
from app.schemas.house import HouseBase

# Auth and Authorization dependencies
from app.services.auth_service import get_current_active_user
from app.core.roles import require_management  # Allows Landlord & Caretaker
from app.routers.properties import get_individual_property
from app.services.house_service import HouseService

router = APIRouter(
    prefix="/properties/{property_id}/houses",
    tags=["Houses"],
    dependencies=[Depends(get_current_active_user)]  # Authenticated baseline
)


@router.get("/all", response_model=List[House])
async def get_all_units_in_property(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    """
    Retrieve units belonging to a property.
    Management sees all units. Tenants are strictly limited to their own active unit.
    """
    if current_user.role_id in [1, 2]:  # Landlord or Caretaker
        return property.houses

    # Tenant scoping
    active_hse_id = await HouseService.get_tenant_active_house_id(session, current_user.id)
    tenant_house = [h for h in property.houses if h.id == active_hse_id]
    
    return tenant_house


@router.get("/{house_id}", response_model=House)
async def get_single_property_unit(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    house_id: UUID
):
    """
    Retrieve details of a single unit. 
    Tenants can only access details of their registered home.
    """
    # Enforce tenant data sandboxing
    await HouseService.verify_user_house_access(session, current_user, house_id)

    statement = select(House).where(
        House.property_id == property.id,
        House.id == house_id,
    )
    house = session.exec(statement).first()

    if not house:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="House could not be found"
        )
    return house


@router.post("/create", response_model=House, status_code=status.HTTP_201_CREATED)
async def create_property_unit(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
    current_user: Annotated[User, Depends(require_management)],  # Restricted
    new_house: HouseBase
):
    """Create a unit under a property (Landlords and Caretakers only)."""
    return await HouseService.create_unit(session, property.id, new_house)


@router.patch("/{house_id}", response_model=House)
async def edit_property_unit(
    session: SessionDep,
    house_id: UUID,
    property: Annotated[Property, Depends(get_individual_property)],
    current_user: Annotated[User, Depends(require_management)],  # Restricted
    house_data: HouseBase
):
    """Edit structural details or base rent of a unit (Landlords and Caretakers only)."""
    return await HouseService.update_unit(session, house_id, house_data)


@router.delete("/{house_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property_unit(
    session: SessionDep,
    house_id: UUID,
    property: Annotated[Property, Depends(get_individual_property)],
    current_user: Annotated[User, Depends(require_management)]  # Restricted
):
    """Permanently remove a housing unit (Landlords and Caretakers only)."""
    await HouseService.delete_unit(session, house_id)
    return None