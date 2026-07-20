# app/services/maintenance_service.py
from uuid import UUID
from sqlmodel import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import List

from app.models.maintenance_bill import MaintenanceBill
from app.models.tenant_unit import TenantUnit
from app.models.house import House
from app.models.property import Property
from app.models.user import User
from app.schemas.maintenance_bill import MaintenanceBillBase, EditMaintenanceStatus, MaintenanceBillUpdate

class MaintenanceService:

    @staticmethod
    async def get_all_requests(session, current_user: User) -> List[MaintenanceBill]:
        """
        Scopes maintenance requests based on who is asking:
        - Landlord (Role 1): Requests for any of their properties.
        - Caretaker (Role 2): Requests for assigned properties.
        - Tenant (Role 3): Only requests linked to their current active house.
        """
        statement = select(MaintenanceBill).join(House).join(Property)

        if current_user.role_id in [1, 2]:  # Landlord or Caretaker
            statement = statement.where(Property.landlord_id == current_user.id)
        else:  # Tenant
            # Find the tenant's current active house unit
            tenant_unit = session.exec(
                select(TenantUnit)
                .where(TenantUnit.tenant_id == current_user.id)
                .where(TenantUnit.rent_end == None)
            ).first()
            if not tenant_unit:
                return []
            statement = statement.where(MaintenanceBill.hse_id == tenant_unit.hse_id)

        statement = statement.options(selectinload(MaintenanceBill.house))
        return session.exec(statement).all()

    @staticmethod
    async def create_request(session, current_user: User, data: MaintenanceBillBase) -> MaintenanceBill:
        """
        Tenants can report issues directly for their units. 
        Landlords/Caretakers can also log requests manually on behalf of houses.
        """
        # If it's a tenant reporting, force the house ID to be their current active house
        target_house_id = data.hse_id
        if current_user.role_id == 3:  # Tenant
            active_unit = session.exec(
                select(TenantUnit)
                .where(TenantUnit.tenant_id == current_user.id)
                .where(TenantUnit.rent_end == None)
            ).first()
            if not active_unit:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No active tenancy found to report a maintenance issue."
                )
            target_house_id = active_unit.hse_id

        # Initialize the record with zeroed operational costs (only added later on resolution)
        db_issue = MaintenanceBill(
            hse_id=target_house_id,
            description=data.description,
            labor_cost=0.0,
            parts_cost=0.0,
            total_amount=0.0,
            status="PENDING"  # Or your default string/enum status
        )
        
        session.add(db_issue)
        session.commit()
        session.refresh(db_issue)
        return db_issue

    @staticmethod
    async def update_status(session, request_id: UUID, status_change: EditMaintenanceStatus) -> MaintenanceBill:
        """Updates the operational progress of a maintenance request."""
        query = select(MaintenanceBill).where(MaintenanceBill.id == request_id).options(selectinload(MaintenanceBill.house))
        issue = session.exec(query).first()
        if not issue:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance issue not found")

        if status_change.status and status_change.status != issue.status:
            issue.status = status_change.status
            session.add(issue)
            session.commit()
            session.refresh(issue)
        return issue

    @staticmethod
    async def update_costs_and_details(
        session, 
        request_id: UUID, 
        update_data: MaintenanceBillUpdate
    ) -> MaintenanceBill:
        """
        Allows management (Landlord/Caretaker) to record actual costs (labor, parts)
        once the repairs are resolved or in progress.
        """
        query = select(MaintenanceBill).where(MaintenanceBill.id == request_id).options(selectinload(MaintenanceBill.house))
        issue = session.exec(query).first()
        if not issue:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance issue not found")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(issue, key, value)

        # Recalculate total landlord maintenance expense dynamically
        issue.total_amount = (issue.labor_cost or 0.0) + (issue.parts_cost or 0.0)

        session.add(issue)
        session.commit()
        session.refresh(issue)
        return issue