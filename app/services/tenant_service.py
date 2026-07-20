# app/services/tenant_service.py
from datetime import datetime, timedelta
from uuid import UUID
from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.exc import IntegrityError

from app.models.tenant import Tenant
from app.models.house import House
from app.models.tenant_unit import TenantUnit
from app.models.user import User
from app.schemas.tenant import TenantCreate, TenantBase
from app.core.security import get_password_hash
from app.services.cascade_delete import delete_tenant_full_cascade

class TenantService:

    @staticmethod
    async def create_tenant_account(session, property_landlord_id: UUID, property_id: UUID, new_tenant: TenantCreate) -> Tenant:
        selected_hse = session.get(House, new_tenant.hse)

        if not selected_hse:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected house is not found")
        
        if selected_hse.property_id != property_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This unit is not available in this property")
        
        if selected_hse.status != "VACANT":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected Unit is unavailable")
        
        try:
            input_data = new_tenant.model_dump()

            # Fix: Role ID is set to 3 (Tenant), not 2 (Caretaker)
            tenant_user = User(
                name=input_data["name"],
                email=input_data["email"],
                tel=input_data["tel"],
                role_id=3,  
                landlord_id=property_landlord_id,
                hashed_password=get_password_hash(input_data["password"]),
            )
            session.add(tenant_user)
            session.flush()

            db_tenant = Tenant(
                name=input_data["name"],
                email=input_data["email"],
                tel=input_data["tel"],
                national_id=input_data["national_id"],
                user_id=tenant_user.id,
            )
            session.add(db_tenant)
            session.flush()
            
            unit_tenant_connection = TenantUnit(
                tenant_id=db_tenant.id,
                hse_id=selected_hse.id,
                rent_begin=datetime.now(),
                rent_end=None
            )
            session.add(unit_tenant_connection)
            
            selected_hse.status = "OCCUPIED"
            session.add(selected_hse)
            session.commit()
            
            session.refresh(db_tenant)
            return db_tenant
            
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A tenant or account with this email already exists")
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    @staticmethod
    async def update_tenant_account(session, tenant: Tenant, tenant_update: TenantBase) -> Tenant:
        tenant_data = tenant_update.model_dump(exclude_unset=True)

        for key, value in tenant_data.items():
            setattr(tenant, key, value)

        # Sync credentials to auth User
        if tenant.user_id:
            linked_user = session.get(User, tenant.user_id)
            if linked_user:
                for key in ("name", "email", "tel"):
                    if key in tenant_data:
                        setattr(linked_user, key, tenant_data[key])
                session.add(linked_user)
            
        if tenant.status == "VACATED":
            # Clean active occupancy associations
            active_units = session.exec(
                select(TenantUnit)
                .where(TenantUnit.tenant_id == tenant.id)
                .where(TenantUnit.rent_end == None)
            ).all()
            for tu in active_units:
                tu.rent_end = datetime.now()
                session.add(tu)
                # Ensure the physical house is vacant again
                house = session.get(House, tu.hse_id)
                if house:
                    house.status = "VACANT"
                    session.add(house)
            
        elif tenant.status == "MOVING OUT":
            active_units = session.exec(
                select(TenantUnit)
                .where(TenantUnit.tenant_id == tenant.id)
                .where(TenantUnit.rent_end == None)
            ).all()
            for tu in active_units:
                tu.rent_end = datetime.now() + timedelta(days=30)
                session.add(tu)

        session.add(tenant)
        try:
            session.commit()
            session.refresh(tenant)
            return tenant
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Another account already uses this email")

    @staticmethod
    async def delete_tenant_account(session, tenant: Tenant) -> None:
        # Reset occupied houses to VACANT
        units = session.exec(select(TenantUnit).where(TenantUnit.tenant_id == tenant.id)).all()
        for unit in units:
            house = session.get(House, unit.hse_id)
            if house:
                house.status = "VACANT"
                session.add(house)

        delete_tenant_full_cascade(session, tenant)
        session.commit()