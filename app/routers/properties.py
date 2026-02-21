from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated, List
from uuid import UUID
from sqlmodel import select

from app.schemas.property import PropertyBase
from app.models.property import Property
from app.db import SessionDep
from app.routers.users import active_user
from app.models.user import User

router = APIRouter(
    prefix="/properties",
    tags=["Properties"],
    dependencies=[Depends(active_user)]
)

@router.get("/all", response_model=List[Property])
async def get_properties_by_landlord(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)]
):
    statement = select(Property).where(Property.landlord_id == current_user.id)
    properties = session.exec(statement).all()

    return properties

@router.get("/{property_id}", response_model=Property)
async def get_individual_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    property_id: UUID
):
    statement = select(Property).where(
        Property.id == property_id,
        Property.landlord_id == current_user.id
    )

    property = session.exec(statement).first()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return property

@router.post("/create", response_model=Property)
async def create_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    property_data: PropertyBase
):
    new_property = property_data.model_dump()
    new_property["landlord_id"] = current_user.id
    property = Property(**new_property)
    session.add(property)
    session.commit()
    session.refresh(property)

    return property

@router.patch("/{property_id}", response_model=Property)
async def edit_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    property_id: UUID,
    property_update: PropertyBase
):
    statement = select(Property).where(
        Property.id == property_id,
        Property.landlord_id == current_user.id
    )

    property = session.exec(statement).first()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")
    
    property_data = property_update.model_dump(exclude_unset=True)

    for key,value in property_data.items():
        setattr(property, key, value)

    session.add(property)
    session.commit()
    session.refresh(property)

    return property