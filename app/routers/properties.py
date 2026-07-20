# app/routers/properties.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated, List
from uuid import UUID
from sqlmodel import select

# Core configuration, DB, roles, and auth dependencies
from app.core.database import SessionDep
from app.core.roles import require_landlord
from app.services.auth_service import get_current_active_user

# Models and Schemas
from app.models.property import Property
from app.models.user import User
from app.schemas.property import PropertyBase

router = APIRouter(
    prefix="/properties",
    tags=["Properties"],
    dependencies=[Depends(get_current_active_user)]
)

@router.get("/all", response_model=List[Property])
async def get_properties_by_landlord(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_landlord)]
):
    """Retrieve all properties owned by the authenticated landlord."""
    statement = select(Property).where(Property.landlord_id == current_user.id)
    properties = session.exec(statement).all()

    return properties

@router.get("/{property_id}", response_model=Property)
async def get_individual_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_landlord)],
    property_id: UUID
):
    """Retrieve a specific property details, scoped to the current landlord."""
    statement = select(Property).where(
        Property.id == property_id,
        Property.landlord_id == current_user.id
    )

    property = session.exec(statement).first()

    if not property:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    
    return property

@router.post("/create", response_model=Property)
async def create_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_landlord)],
    property_data: PropertyBase
):
    """Create a new property under the landlord's account."""
    new_property_data = property_data.model_dump()
    new_property_data["landlord_id"] = current_user.id
    
    property = Property(**new_property_data)
    session.add(property)
    session.commit()
    session.refresh(property)

    return property

@router.patch("/{property_id}", response_model=Property)
async def edit_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_landlord)],
    property_id: UUID,
    property_update: PropertyBase
):
    """Update property details dynamically, locked to the landlord who owns it."""
    statement = select(Property).where(
        Property.id == property_id,
        Property.landlord_id == current_user.id
    )

    property = session.exec(statement).first()

    if not property:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    
    property_data = property_update.model_dump(exclude_unset=True)

    for key, value in property_data.items():
        setattr(property, key, value)

    session.add(property)
    session.commit()
    session.refresh(property)

    return property