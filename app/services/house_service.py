# app/services/house_service.py
from uuid import UUID
from sqlmodel import select
from fastapi import HTTPException, status

from app.models.house import House
from app.models.tenant_unit import TenantUnit
from app.models.user import User
from app.schemas.house import HouseBase

class HouseService:

    @staticmethod
    async def get_tenant_active_house_id(session, tenant_id: UUID) -> UUID | None:
        """Helper to fetch the active unit ID of a logged-in tenant."""
        active_unit = session.exec(
            select(TenantUnit)
            .where(TenantUnit.tenant_id == tenant_id)
            .where(TenantUnit.rent_end == None)
        ).first()
        return active_unit.hse_id if active_unit else None

    @classmethod
    async def verify_user_house_access(cls, session, current_user: User, house_id: UUID) -> None:
        """
        Ensures Tenants can only query their own active home.
        Management (Landlord/Caretaker) passes this check by default (property validation handled by dependencies).
        """
        if current_user.role_id == 3:  # Tenant
            active_hse_id = await cls.get_tenant_active_house_id(session, current_user.id)
            if not active_hse_id or active_hse_id != house_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. You can only view the unit you currently reside in."
                )

    @staticmethod
    async def create_unit(session, property_id: UUID, new_house: HouseBase) -> House:
        house_data = new_house.model_dump()
        house_data["property_id"] = property_id
        
        house = House(**house_data)
        session.add(house)
        session.commit()
        session.refresh(house)
        return house

    @staticmethod
    async def update_unit(session, house_id: UUID, house_data: HouseBase) -> House:
        house = session.get(House, house_id)
        if not house:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="House unit not found."
            )
            
        house_edit = house_data.model_dump(exclude_unset=True)
        for key, value in house_edit.items():
            setattr(house, key, value)

        session.add(house)
        session.commit()
        session.refresh(house)
        return house

    @staticmethod
    async def delete_unit(session, house_id: UUID) -> None:
        house = session.get(House, house_id)
        if not house:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="House unit not found."
            )
        session.delete(house)
        session.commit()