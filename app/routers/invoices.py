import pandas as pd

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import select
from sqlalchemy import and_
from sqlalchemy.orm import selectinload
from typing import List, Annotated
from uuid import UUID
from datetime import datetime, timedelta

from app.db import SessionDep
from app.models.tenant import Tenant
from app.models.house import House
from app.models.tenant_unit import TenantUnit
from app.models.property import Property
from app.models.user import User
from app.models.invoice import Invoice
from app.models.maintenance_bill import MaintenanceBill
from app.models.utility import UtilityBill
from app.schemas.invoice import InvoiceGenerationRequest, InvoiceRead
from app.schemas.utility import BillType
from app.schemas.tenant import TenantStatus
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
    statement = select(Invoice).join(TenantUnit, Invoice.tenant_unit_id == TenantUnit.id).join(House, House.id == TenantUnit.hse_id).join(Property, Property.id == House.property_id).where(Property.landlord_id == current_user.id)
    
    if hse_id:
        statement = statement.where(Invoice.tenant_unit.hse_id == hse_id)
        
    if tenant_id:
        statement = statement.where(Invoice.tenant_unit.tenant_id == tenant_id)

    statement = statement.options(selectinload(Invoice.tenant_unit).selectinload(TenantUnit.house), selectinload(Invoice.tenant_unit).selectinload(TenantUnit.tenant), selectinload(Invoice.utilities))

    invoices = session.exec(statement).all()

    return invoices

@router.get("/rent/{invoice_id}", response_model=Invoice)
async def show_single_invoice(
    session: SessionDep,
    invoice_id: UUID
):
    statement = select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.tenant_unit).selectinload(TenantUnit.house), selectinload(Invoice.tenant_unit).selectinload(TenantUnit.tenant), selectinload(Invoice.utilities))

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
    
    tenant_unit = session.exec(select(TenantUnit).where(TenantUnit.hse_id == house.id)).first()

    tenant_statement = select(Tenant).join(TenantUnit, TenantUnit.hse_id == house.id and TenantUnit.rent_end == None).where(tenant_unit.tenant_id == Tenant.id)
    tenant = session.exec(tenant_statement).first()
    
    if tenant.wallet_balance > 0.0:
        bal = tenant.wallet_balance        

    invoice = Invoice(
        tenant_unit_id=tenant_unit.id,
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
):
    statement = select(MaintenanceBill).join(House).join(Property).where(Property.landlord_id == current_user.id)
    
    if hse_id:
        statement = statement.where(MaintenanceBill.hse_id == hse_id)
        
    statement = statement.options(selectinload(MaintenanceBill.house))
    
    mbs = session.exec(statement).all()
    
    return mbs

@router.post("/generate/maintenance/", response_model=MaintenanceBill)
async def generate_tenant_maintenance_bill(
    session: SessionDep,
    new_bill: MaintenanceBillBase
):
    bill = new_bill.model_dump()
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

@router.post("/rent/bulk/upload")
async def bulk_upload_old_rent_invoices(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    property_id: UUID,
    file: UploadFile = File(...)
):
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Invalid File format. Please upload CSV or Excel")
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file.file)
            df = {"CSV_Data" : df}
        else:
            df = pd.read_excel(file.file, sheet_name=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {str(e)}")
    
    try:
        new_invoices = []
        
        houses_statement = (
            select(House)
            .where(House.property_id == property_id)
        )
        units = session.exec(houses_statement).all()
        units_dict = {unit.number : unit for unit in units}
        tenants_statement = (
            select(Tenant).join(TenantUnit).join(House, House.property_id == property_id)
        )
        tenants = session.exec(tenants_statement).all()
        tenants_dict = {tenant.name: tenant for tenant in tenants}
        
        tenant_units = session.exec(
            select(TenantUnit).join(House, House.property_id == property_id)
        ).all()
        tenant_units_dict = {(tu.hse_id, tu.tenant_id): tu for tu in tenant_units}
        
        for sheet_month_name, month_df in df.items():
            required_cols = ["hse_number", "tenant_name", "contact_info", "water_bill", "electricity_bill", "other_utility_bill"]
            if not all(col in month_df.columns for col in required_cols):
                missing_cols = [col for col in required_cols if col not in month_df.columns]
                    
                    # Fix the f-string to use month_df (the actual dataframe)
                raise HTTPException(
                    status_code=400, 
                    detail=f"Missing required columns: {missing_cols}. Columns found in sheet: {list(month_df.columns)}"
                )
        
            month_df["water_bill"] = pd.to_numeric(month_df["water_bill"], errors="coerce").fillna(0)
            month_df["electricity_bill"] = pd.to_numeric(month_df["electricity_bill"], errors="coerce").fillna(0)
            month_df["other_utility_bill"] = pd.to_numeric(month_df["other_utility_bill"], errors="coerce").fillna(0)
                
            for index, row in month_df.iterrows(): 
                # tenant _unit exists
                hse = units_dict.get(str(row["hse_number"]))
                if not hse:
                    raise Exception("House not found in DB!")
                
                tenant = tenants_dict.get(str(row["tenant_name"]))
                
                tu = None
                if tenant:
                    tu = tenant_units_dict.get((hse.id, tenant.id))
                    
                month_number = datetime.strptime(sheet_month_name.lower(), "%b").month                
                date_of_gen = datetime(2026, month_number, 2)
                utilities_total: float = float(row["water_bill"]) + float(row["electricity_bill"]) + float(row["other_utility_bill"])
                if tu:
                    invoice_dict = {
                        "tenant_unit_id" : tu.id,
                        "rent_amount" : hse.rent,
                        "amount": hse.rent + utilities_total,
                        "date_of_gen" : date_of_gen,
                        "date_due" : date_of_gen + timedelta(days=7)
                    }
                    invoice_to_save = Invoice(**invoice_dict)
                    session.add(invoice_to_save)
                    session.flush()
                    
                    water_utility_bill = UtilityBill(
                        bill_type=BillType.WATER,
                        amount=float(row["water_bill"]),
                        invoice_id=invoice_to_save.id
                    )
                    
                    electricity_utility_bill = UtilityBill(
                        bill_type=BillType.ELECTRICITY,
                        amount=float(row["electricity_bill"]),
                        invoice_id=invoice_to_save.id
                    )
                    
                    other_utility_bill = UtilityBill(
                        bill_type=BillType.OTHER,
                        amount=float(row["other_utility_bill"]),
                        invoice_id=invoice_to_save.id
                    )
                    
                    session.add(water_utility_bill)
                    session.add(electricity_utility_bill)
                    session.add(other_utility_bill)
                    
                    new_invoices.append(invoice_to_save)
                # tenant_unit is changed
                elif tu not in tenant_units_dict:
                    if not tenant:
                        # tenant_email = str(row["tenant_email"])
                        tenant = Tenant(
                            name=str(row["tenant_name"]),
                            email=None,
                            tel=str(row["contact_info"]),
                            national_id=None,
                            status=TenantStatus.VACATED
                        )
                        
                        session.add(tenant)
                        session.flush()
                        
                        tenants_dict[tenant.name] = tenant
                        
                    new_tenant_unit = TenantUnit(
                        tenant_id=tenant.id,
                        hse_id=hse.id,
                        rent_begin=datetime(2026, month_number, 1),
                    )
                    session.add(new_tenant_unit)
                    session.flush()
                    invoice_dict = {
                        "tenant_unit_id" : new_tenant_unit.id,
                        "rent_amount" : hse.rent,
                        "amount": hse.rent + utilities_total,
                        "date_of_gen" : date_of_gen,
                        "date_due" : date_of_gen + timedelta(days=7)
                    }
                    invoice_to_save = Invoice(**invoice_dict)
                    session.add(invoice_to_save)
                    session.flush()
                    
                    water_utility_bill = UtilityBill(
                        bill_type=BillType.WATER,
                        amount=float(row["water_bill"]),
                        invoice_id=invoice_to_save.id
                    )
                    
                    electricity_utility_bill = UtilityBill(
                        bill_type=BillType.ELECTRICITY,
                        amount=float(row["electricity_bill"]),
                        invoice_id=invoice_to_save.id
                    )
                    
                    other_utility_bill = UtilityBill(
                        bill_type=BillType.OTHER,
                        amount=float(row["other_utility_bill"]),
                        invoice_id=invoice_to_save.id
                    )
                    
                    session.add(water_utility_bill)
                    session.add(electricity_utility_bill)
                    session.add(other_utility_bill)
                    
                    new_invoices.append(invoice_to_save)
                    tenant_units_dict[(hse.id, tenant.id)] = new_tenant_unit
                    
        session.commit() 
        
        return { "message" : "Invoices successfully created", "count": len(new_invoices) }
    
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing row {index}: {str(e)}")