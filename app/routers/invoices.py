from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlalchemy.orm import selectinload
from typing import List, Annotated
from uuid import UUID
from datetime import datetime, timedelta

from app.db import SessionDep
from app.models.tenant import Tenant
from app.models.house import House
from app.models.property import Property
from app.models.user import User
from app.models.invoice import Invoice
from app.models.maintenance_bill import MaintenanceBill
from app.models.utility import UtilityBill
from app.schemas.invoice import InvoiceGenerationRequest, InvoiceRead
from app.schemas.maintenance_bill import MaintenanceBillBase, MaintenanceBillRead, MaintenanceBillUpdate
from app.routers.users import active_user
from app.routers.properties import get_individual_property


router = APIRouter(
    prefix="/invoices",
    tags=["Invoices"],
    dependencies=[Depends(active_user)]
)

@router.get("/rent/all", response_model=List[InvoiceRead])
async def get_all_invoices(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    hse_id: UUID | None = None,
    tenant_id: UUID | None = None
):
    statement = select(Invoice).join(House, House.id == Invoice.hse_id).join(Property, Property.id == House.property_id).where(Property.landlord_id == current_user.id)
    
    if hse_id:
        statement = statement.where(Invoice.hse_id == hse_id)
        
    if tenant_id:
        statement = statement.where(Invoice.tenant_id == tenant_id)

    statement = statement.options(selectinload(Invoice.house), selectinload(Invoice.utilities), selectinload(Invoice.tenant))

    invoices = session.exec(statement).all()

    return invoices

@router.get("/rent/{invoice_id}", response_model=Invoice)
async def show_single_invoice(
    session: SessionDep,
    invoice_id: UUID
):
    statement = select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.house), selectinload(Invoice.utilities), selectinload(Invoice.tenant))

    invoice = session.exec(statement).first()

    return invoice

@router.post("/generate/rent/{hse_id}", response_model=Invoice)
async def generate_tenant_rent_invoices(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    utility_list: InvoiceGenerationRequest,
    hse_id: UUID
):
    house: House = session.get(House, hse_id)

    if not house:
        raise HTTPException(status_code=404, detail="House not found!")

    property_statement = select(Property).where(Property.id == house.property_id )
    property = session.exec(property_statement).first()

    if property.landlord_id != current_user.id:
        raise HTTPException(status_code=401, detail="Unauthorized!")

    base_rent: float = house.rent
    utilities_total: float = sum(u.amount for u in utility_list.utilities) 
    bal: float = 0

    tenant_statement = select(Tenant).where(Tenant.hse == house.id)
    tenant = session.exec(tenant_statement).first()
    
    if tenant.wallet_balance > 0.0:
        bal = tenant.wallet_balance        

    invoice = Invoice(
        tenant_id=tenant.id,
        hse_id=house.id,
        rent_amount=house.rent,
        amount=(base_rent+utilities_total)- bal,
        date_due=datetime.now()+timedelta(days=7),
    )

    session.add(invoice)
    session.commit()
    session.refresh(invoice)

    for util in utility_list.utilities:
        saving_util = UtilityBill(
            **util.model_dump(),
            invoice_id=invoice.id
        )

        session.add(saving_util)
    session.commit()
    session.refresh(invoice)

    return invoice  

@router.patch("/rent/{invoice_id}/edit", response_model=Invoice)
async def edit_specific_rent_invoice(
    session: SessionDep,
    invoice_id: UUID,
    current_user: Annotated[User, Depends(active_user)],
    utility_list: InvoiceGenerationRequest
):
    query = select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.house), selectinload(Invoice.utilities), selectinload(Invoice.tenant))
    invoice = session.exec(query).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Could not find specific invoice")
    
    if current_user.role != 1:
        raise HTTPException(status_code=403, detail="Unauthorized User")
    
    utilities_updates = {u.bill_type: u.amount for u in utility_list.utilities}
    
    current_utilities_total = 0.0
    
    for db_util in invoice.utilities:
        if db_util.bill_type in utilities_updates:
            db_util.amount = utilities_updates[db_util.bill_type]
            session.add(db_util)
            
        current_utilities_total += db_util.amount
        
    invoice.amount = invoice.rent_amount + current_utilities_total
    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    
    return invoice

@router.get("/maintenance/all", response_model=List[MaintenanceBillRead])
async def get_all_maintenance_bills(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    hse_id: UUID | None = None,
    # tenant_id: UUID | None = None
):
    statement = select(MaintenanceBill).join(House).join(Property).where(Property.landlord_id == current_user.id)
    
    if hse_id:
        statement = statement.where(MaintenanceBill.hse_id == hse_id)
        
    # if tenant_id:
    #     statement = statement.where(MaintenanceBill.tenant_id == tenant_id)
        
    statement = statement.options(selectinload(MaintenanceBill.house))
    
    mbs = session.exec(statement).all()
    
    return mbs

@router.post("/generate/maintenance/", response_model=MaintenanceBill)
async def generate_tenant_maintenance_bill(
    session: SessionDep,
    new_bill: MaintenanceBillBase
):
    bill = new_bill.model_dump()
    # qry = select(Tenant).where(Tenant.hse == bill["hse_id"])
    # tenant = session.exec(qry).first()
    # if tenant:
    #     bill["tenant_id"] = tenant.id
    # print(bill)
    bill["total_amount"] = bill["labor_cost"] + bill["parts_cost"]
    db_bill = MaintenanceBill(**bill)
    session.add(db_bill)
    session.commit()
    session.refresh(db_bill)
    
    return db_bill

@router.patch("/maintenance/{maintenance_bill_id}/edit", response_model=MaintenanceBill)
async def edit_specific_maintenance_bill(
    session: SessionDep,
    maintenance_bill_id: UUID,
    edit_bill: MaintenanceBillUpdate
):
    query = select(MaintenanceBill).where(MaintenanceBill.id == maintenance_bill_id).options(selectinload(MaintenanceBill.house))
    mb = session.exec(query).first()
    if not mb:
        raise HTTPException(status_code=404, detail="Maintenance bill could not be found")
    
    bill = edit_bill.model_dump(exclude_unset=True)
    
    for key,value in bill.items():
        setattr(mb, key, value)
        
    mb.total_amount = mb.labor_cost + mb.parts_cost
    
    session.add(mb)
    session.commit()
    session.refresh(mb)
    
    return mb
