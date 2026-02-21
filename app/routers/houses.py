from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from typing import List, Annotated
from uuid import UUID

from app.db import SessionDep
from app.models.property import Property
from app.models.house import House
from app.schemas.house import HouseBase
from app.routers.users import active_user
from app.routers.properties import get_individual_property

router = APIRouter(
    prefix="/properties/{property_id}/houses",
    tags=["Houses"],
    dependencies=[Depends(active_user)]
)

@router.get("/all", response_model=List[House])
async def get_all_units_in_property(
    property: Annotated[Property, Depends(get_individual_property)],
):
    return property.houses

@router.get("/{house_id}", response_model=House)
async def get_single_property_unit(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
    house_id: UUID
):
    statement = select(House).where(
        House.property_id == property.id,
        House.id == house_id,
    )

    house = session.exec(statement).first()

    if not house:
        raise HTTPException(
            status_code=404,
            detail= "House could not be found"
        )
    
    return house

@router.post("/create", response_model=House)
async def create_property_unit(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
    new_house: HouseBase
):
    house_data = new_house.model_dump()
    house_data["property_id"] = property.id
    house = House(**house_data)
    session.add(house)
    session.commit()
    session.refresh(house)

    return house

@router.patch("/{house_id}", response_model=House)
async def edit_property_unit(
    session: SessionDep,
    house: Annotated[House, Depends(get_single_property_unit)],
    house_data: HouseBase
):
    house_edit = house_data.model_dump(exclude_unset=True)

    for key,value in house_edit.items():
        setattr(house, key, value)

    session.add(house)
    session.commit()
    session.refresh(house)

    return house