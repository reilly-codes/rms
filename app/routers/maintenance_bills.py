# app/routers/maintenance_bills.py
from fastapi import APIRouter, Depends, status
from typing import Annotated, List
from uuid import UUID

from app.core.database import SessionDep
from app.models.user import User
from app.models.maintenance_bill import MaintenanceBill
from app.schemas.maintenance_bill import (
    MaintenanceBillBase, 
    MaintenanceBillRead, 
    EditMaintenanceStatus, 
    MaintenanceBillUpdate
)
from app.services.auth_service import get_current_active_user
from app.core.roles import require_management  # Restricts updates to Landlord/Caretaker
from app.services.maintenance_service import MaintenanceService

router = APIRouter(
    prefix="/maintenance",
    tags=["Repairs and Maintenance"],
    dependencies=[Depends(get_current_active_user)]  # Everyone logged in can access base paths
)


@router.get("/all", response_model=List[MaintenanceBillRead])
async def get_all_maintenance_requests(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    """
    Fetch maintenance history. 
    Tenants see their active unit requests, landlords/caretakers see all property tasks.
    """
    return await MaintenanceService.get_all_requests(session, current_user)


@router.post("/report", response_model=MaintenanceBillRead, status_code=status.HTTP_201_CREATED)
async def report_new_maintenance_issue(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    new_issue: MaintenanceBillBase
):
    """
    Allows tenants to lodge issues (tap leaking, broken latch).
    Landlords/Caretakers can also log on behalf of any unit.
    """
    return await MaintenanceService.create_request(session, current_user, new_issue)


@router.patch("/edit-status/{maintenance_id}", response_model=MaintenanceBillRead)
async def edit_maintenance_issue_status(
    session: SessionDep,
    maintenance_id: UUID,
    current_user: Annotated[User, Depends(require_management)],
    status_change: EditMaintenanceStatus
):
    """Update progress status (e.g. PENDING -> IN_PROGRESS -> COMPLETED)."""
    return await MaintenanceService.update_status(session, maintenance_id, status_change)


@router.patch("/update-costs/{maintenance_id}", response_model=MaintenanceBillRead)
async def update_maintenance_operational_costs(
    session: SessionDep,
    maintenance_id: UUID,
    current_user: Annotated[User, Depends(require_management)],
    update_data: MaintenanceBillUpdate
):
    """
    Record labor and parts expenditure for the repair.
    Keeps a record of landlord expenses without generating bills for tenants.
    """
    return await MaintenanceService.update_costs_and_details(session, maintenance_id, update_data)