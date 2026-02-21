from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlalchemy.orm import selectinload
from typing import Annotated, List
from uuid import UUID

from app.db import SessionDep
from app.routers.users import active_user
from app.models.user import User
from app.models.property import Property
from app.models.house import House
from app.models.maintenance_bill import MaintenanceBill
from app.schemas.maintenance_bill import MaintenanceBillBase, MaintenanceBillRead, EditMaintenanceStatus

router = APIRouter(
    prefix="/maintenance",
    tags=["Repairs"],
    dependencies=[Depends(active_user)]
)


@router.get("/all", response_model=List[MaintenanceBillRead], response_model_exclude={"labor_cost", "parts_cost", "total_amount"})
async def get_maintenance_issues(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)]
):
    qry = select(MaintenanceBill).join(House).join(Property).where(Property.landlord_id == current_user.id).options(selectinload(MaintenanceBill.house))
    
    response = session.exec(qry).all()
    
    return response

@router.patch("/edit-status/{maintenance_id}" ,response_model=MaintenanceBillRead,  response_model_exclude={"labor_cost", "parts_cost", "total_amount"})
async def edit_maintenance_issue_status(
    session: SessionDep,
    maintenance_id: UUID,
    status_change: EditMaintenanceStatus
):
    maintenance_qry = select(MaintenanceBill).where(MaintenanceBill.id == maintenance_id).options(selectinload(MaintenanceBill.house))
    maintenance_issue = session.exec(maintenance_qry).first()
    
    if not maintenance_issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Could not find Maintenace Issue")
    
    if status_change.status == None or status_change.status == maintenance_issue.status:
        return maintenance_issue
    
    maintenance_issue.status = status_change.status
    
    session.add(maintenance_issue)
    session.commit()
    session.refresh(maintenance_issue)
    
    return maintenance_issue

@router.post("/generate/", response_model=MaintenanceBillRead,  response_model_exclude={"labor_cost", "parts_cost", "total_amount"})
async def generate_maintenance_request(
    session: SessionDep,
    new_bill: MaintenanceBillBase
):
    bill = new_bill.model_dump()
    # qry = select(Tenant).where(Tenant.hse == bill["hse_id"])
    # tenant = session.exec(qry).first()
    # if tenant:
    #     bill["tenant_id"] = tenant.id
    
    db_bill = MaintenanceBill(**bill)
    session.add(db_bill)
    session.commit()
    session.refresh(db_bill)
    
    bill_qry = select(MaintenanceBill).where(MaintenanceBill.id == db_bill.id).options(selectinload(MaintenanceBill.house))
    
    response = session.exec(bill_qry).first()
    
    return response