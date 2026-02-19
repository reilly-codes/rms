import pandas as pd

from fastapi import FastAPI, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List, Optional
from datetime import timedelta, datetime
from sqlmodel import select, or_
from sqlalchemy.orm import selectinload
from uuid import UUID
from pywa_async import WhatsApp, types

from models import (
    Token,
    User,
    LoginRequest,
    UserCreate,
    UserPublic,
    Property,
    PropertyBase,
    House,
    HouseBase,
    TenantBase,
    Tenant,
    InvoiceBase,
    Invoice,
    InvoiceGenerationRequest,
    InvoiceRead,
    TransactionStatus,
    Transaction,
    PaymentBase,
    Payment,
    PaymentStatus,
    UtilityBillBase,
    UtilityBill,
    MaintenanceBillBase, 
    MaintenanceBill,
    MaintenanceBillRead,
    PasswordChange,
    EditMaintenanceStatus,
    BroadcastBase, 
    Broadcast
)

from auth import (
    authenticate_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_active_user,
    get_password_hash,
    change_password
)

from db import (
    SessionDep,
    lifespan,
)

app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,   
    allow_credentials=True,  
    allow_methods=["*"],     
    allow_headers=["*"],     
)

wa = WhatsApp(
    phone_id="",
    token="",
)

@app.post("/token", response_model=Token)
async def login_for_access_token(
    login_data: LoginRequest,
    session: SessionDep
):
    user = authenticate_user(session, login_data.email, login_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Login details",
            headers={"WWW-Authenticate" : "Bearer"},
        )
    
    access_token_expiry = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub" : user.id,
            "role_id" : user.role_id
        },
        expires_delta=access_token_expiry
    )

    return Token(access_token=access_token, token_type="bearer")

@app.get("/users/current", response_model=User)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    return current_user

@app.post("/users/create", response_model=UserPublic)
async def register_user(user_in: UserCreate, session: SessionDep):
    user_data = user_in.model_dump()
    plain_password = user_data.pop("password")
    user_data["hashed_password"] = get_password_hash(plain_password)
    user = User(**user_data)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@app.post("/change-password")
async def change_user_password(
    password_data: PasswordChange,
    current_user: Annotated[User, Depends(read_users_me)],
    session: SessionDep
):
    return await change_password(password_data, current_user, session)

@app.get("/properties/all", response_model=List[Property])
async def get_properties_by_landlord(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)]
):
    statement = select(Property).where(Property.landlord_id == current_user.id)
    properties = session.exec(statement).all()

    return properties

@app.get("/properties/{property_id}", response_model=Property)
async def get_individual_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
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

@app.post("/properties/create", response_model=Property)
async def create_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    property_data: PropertyBase
):
    new_property = property_data.model_dump()
    new_property["landlord_id"] = current_user.id
    property = Property(**new_property)
    session.add(property)
    session.commit()
    session.refresh(property)

    return property

@app.patch("/properties/{property_id}", response_model=Property)
async def edit_property(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
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

@app.get("/properties/{property_id}/houses/all", response_model=List[House])
async def get_all_units_in_property(
    property: Annotated[Property, Depends(get_individual_property)],
):
    return property.houses

@app.get("/properties/{property_id}/houses/{house_id}", response_model=House)
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

@app.post("/properties/{property_id}/houses/create", response_model=House)
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

@app.patch("/properties/{property_id}/houses/{house_id}", response_model=House)
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

@app.get("/tenants/all", response_model=List[Tenant])
async def get_all_tenants(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    property_id: UUID | None = None
):
    statement = select(Tenant).join(House, Tenant.hse == House.id).join(Property, House.property_id == Property.id).where(Property.landlord_id == current_user.id)
    
    if property_id:
        statement = statement.where(House.property_id == property_id)

    tenants = session.exec(statement).all()

    return tenants

@app.get("/tenants/{tenant_id}", response_model=Tenant)
async def get_single_tenant(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    tenant_id: UUID
):
    statement = select(Tenant).join(House, Tenant.hse == House.id).join(Property, House.property_id == Property.id).where(Property.landlord_id == current_user.id).where(Tenant.id == tenant_id)

    tenant = session.exec(statement).first()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenanty

@app.post("/tenants/create/properties/{property_id}", response_model=Tenant)
async def create_tenant(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
    newTenant: TenantBase,
):
    
    selected_hse = session.get(House, newTenant.hse)

    if not selected_hse :
        raise HTTPException(status_code=404, detail="Selected house is not found")
    
    if selected_hse.property_id != property.id:
        raise HTTPException(status_code=400, detail="This unit is not available in this property")
    
    if selected_hse.status != "VACANT":
        raise HTTPException(status_code=400, detail="Selected Unit is unavailable")
    
    dbTenant = Tenant.model_validate(newTenant)
    session.add(dbTenant)
    selected_hse.status = "OCCUPIED"
    session.add(selected_hse)
    session.commit()
    session.refresh(dbTenant)

    return dbTenant

@app.patch("/tenants/{tenant_id}/edit", response_model=Tenant)
async def edit_tenant_details(
    session: SessionDep,
    tenant: Annotated[Tenant, Depends(get_single_tenant)],
    tenantUpdate: TenantBase
):
    tenantData = tenantUpdate.model_dump(exclude_unset=True)

    for key,value in tenantData.items():
        setattr(tenant, key, value)

    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    return tenant
    
@app.get("/landlords/units/all", response_model=List[House])
async def get_all_landlord_units(session: SessionDep, current_user: Annotated[User, Depends(read_users_me)]):
    statement = (
        select(House)
        .join(Property, House.property_id == Property.id)
        .where(Property.landlord_id == current_user.id)
    )
    units = session.exec(statement).all()
    return units

@app.get("/invoices/rent/all", response_model=List[InvoiceRead])
async def get_all_invoices(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
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

@app.get("/invoices/{invoice_id}", response_model=Invoice, dependencies=[Depends(read_users_me)])
async def show_single_invoice(
    session: SessionDep,
    invoice_id: UUID
):
    statement = select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.house), selectinload(Invoice.utilities), selectinload(Invoice.tenant))

    invoice = session.exec(statement).first()

    return invoice

@app.post("/invoice/generate/rent/{hse_id}", response_model=Invoice)
async def generate_tenant_rent_invoices(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
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

@app.patch("/invoices/rent/{invoice_id}/edit", response_model=Invoice)
async def edit_specific_rent_invoice(
    session: SessionDep,
    invoice_id: UUID,
    current_user: Annotated[User, Depends(read_users_me)],
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

@app.get("/invoices/maintenance/all", response_model=List[MaintenanceBillRead])
async def get_all_maintenance_bills(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    hse_id: UUID | None = None,
    tenant_id: UUID | None = None
):
    statement = select(MaintenanceBill).join(House).join(Property).where(Property.landlord_id == current_user.id)
    
    if hse_id:
        statement = statement.where(MaintenanceBill.hse_id == hse_id)
        
    if tenant_id:
        statement = statement.where(MaintenanceBill.tenant_id == tenant_id)
        
    statement = statement.options(selectinload(MaintenanceBill.payments), selectinload(MaintenanceBill.tenant), selectinload(MaintenanceBill.house))
    
    mbs = session.exec(statement).all()
    
    return mbs

@app.post("/invoices/generate/maintenance/", response_model=MaintenanceBill, dependencies=[Depends(read_users_me)])
async def generate_tenant_maintenance_bill(
    session: SessionDep,
    new_bill: MaintenanceBillBase
):
    bill = new_bill.model_dump()
    qry = select(Tenant).where(Tenant.hse == bill["hse_id"])
    tenant = session.exec(qry).first()
    if tenant:
        bill["tenant_id"] = tenant.id
    print(bill)
    bill["total_amount"] = bill["labor_cost"] + bill["parts_cost"]
    db_bill = MaintenanceBill(**bill)
    session.add(db_bill)
    session.commit()
    session.refresh(db_bill)
    
    return db_bill

@app.patch("/invoices/maintenance/{maintenance_bill_id}/edit", response_model=MaintenanceBill, dependencies=[Depends(read_users_me)])
async def edit_specific_maintenance_bill(
    session: SessionDep,
    maintenance_bill_id: UUID,
    edit_bill: MaintenanceBillBase
):
    query = select(MaintenanceBill).where(MaintenanceBill.id == maintenance_bill_id).options(selectinload(MaintenanceBill.house), selectinload(MaintenanceBill.tenant))
    mb = session.exec(query).first()
    if not mb:
        raise HTTPException(status_code=404, detail="Maintenance bill xould not be found")
    
    bill = edit_bill.model_dump(exclude_unset=True)
    
    for key,value in bill.items():
        setattr(mb, key, value)
    
    session.add(mb)
    session.commit()
    session.refresh(mb)
    
    return mb

@app.get("/payments/all", response_model=List[Payment])
async def get_all_payments(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    hse_id: UUID | None = None,
    tenant_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None
):
    statement = select(Payment).join(Invoice, isouter=True).join(MaintenanceBill, isouter=True)
    
    if hse_id:
        statement = statement.where(
            (Invoice.hse_id == hse_id) | (MaintenanceBill.hse_id == hse_id)
        )
        
    if tenant_id:
        statement = statement.where(
            (Invoice.tenant_id == tenant_id) | (MaintenanceBill.tenant_id == tenant_id)
        )
        
    statement = statement.join(House, (House.id == Invoice.hse_id) | (House.id == MaintenanceBill.hse_id), isouter=True)
    statement = statement.join(Property, Property.id == House.property_id, isouter=True)
    statement = statement.where(Property.landlord_id == current_user.id)
    
    payments = session.exec(statement).unique().all()
    
    return payments

@app.post("/process/payment", response_model=Payment)
async def create_payment(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    new_payment: PaymentBase
):
    payment = new_payment.model_dump()
    payment["created_by"] = current_user.id
    
    db_payment = Payment(**payment)
    
    session.add(db_payment)
    session.commit()
    session.refresh(db_payment)
    
    return db_payment

@app.patch("/edit/payment/{payment_id}", response_model=Payment, dependencies=[Depends(read_users_me)])
async def edit_payment(
    session: SessionDep,
    payment_id: UUID,
    payment: PaymentBase
):
    existing_payment = session.get(Payment, payment_id)
    
    if not existing_payment:
        raise HTTPException(status_code=404, detail="Payment could not be found")
    
    pm = payment.model_dump(exclude_unset=True)
    
    for key, value in pm.items():
        setattr(existing_payment, key, value)
        
    session.add(existing_payment)
    session.commit()
    session.refresh(existing_payment)
    
    return existing_payment

@app.get("/transactions/all", response_model=List[Transaction], dependencies=[Depends(read_users_me)])
async def get_all_transactions(
    session: SessionDep,
    status: TransactionStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None
):
    query = select(Transaction)
    
    if status:
        query = query.where(Transaction.transaction_status == status)
        
    if date_from:
        query = query.where(Transaction.transaction_date >= date_from)
    elif date_from and date_to:
        query = query.where(Transaction.transaction_date >= date_from and Transaction.transaction_date <= date_to)
        
    query = query.order_by(Transaction.transaction_date)
    
    transactions = session.exec(query).all()
    
    return transactions
        
    
@app.post("/transactions/upload", dependencies=[Depends(read_users_me)])
async def upload_bank_statement(
    session: SessionDep,
    file: UploadFile = File(...)
):
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Invalid File format. Please upload CSV or Excel")
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file.file)
        else:
            df = pd.read_excel(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {str(e)}")
    
    required_cols = ["Date", "Amount", "Reference"]
    if not all(col in df.columns for col in required_cols):
        raise HTTPException(status_code=400, detail=f"Missing required columns. Found: {df.columns}")
    
    try: 
        new_transactions = []
        for index, row in df.iterrows():
            existing_qry = select(Transaction).where(Transaction.transaction_reference == str(row["Reference"]))
            existing = session.exec(existing_qry).first()
            
            if existing:
                continue
            
            txn = Transaction(
                transaction_reference=str(row["Reference"]),
                transaction_date=pd.to_datetime(row["Date"]),
                amount=float(row["Amount"])
            )
            
            session.add(txn)
            new_transactions.append(txn)
        
        session.commit()
        return {"message": "Success", "count": len(new_transactions)}
    
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing row {index}: {str(e)}")
    
@app.post("/reconciliation/run", dependencies=[Depends(read_users_me)])  
async def reconciliation(
    session: SessionDep
):
    payments_query = select(Payment).where(Payment.status == PaymentStatus.UNVERIFIED)
    payments = session.exec(payments_query).all()
    
    txn_query = select(Transaction).where(Transaction.transaction_status == TransactionStatus.PENDING)
    txn = session.exec(txn_query).all()
    
    txn_map = {t.transaction_reference.strip().upper(): t for t in txn}
    matched_count = 0
    
    for payment in payments:
        if payment.transaction_ref.strip().upper() in txn_map:
            matched_txn = txn_map[payment.transaction_ref]
            payment.transaction_id = matched_txn.id
            payment.status = PaymentStatus.VERIFIIED
            matched_txn.transaction_status = TransactionStatus.MATCHED
            
            session.add(payment)
            session.add(matched_txn)
            
            matched_count += 1
            
    session.commit()
    
    return {
        "status": "success", 
        "matches_found": matched_count,
        "remaining_unverified": len(payments) - matched_count
    }
    
@app.get("/maintenance/all", response_model=List[MaintenanceBillRead], response_model_exclude={"labor_cost", "parts_cost", "total_amount"})
async def get_maintenance_issues(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)]
):
    qry = select(MaintenanceBill).join(House).join(Property).where(Property.landlord_id == current_user.id).options(selectinload(MaintenanceBill.house), selectinload(MaintenanceBill.tenant))
    
    response = session.exec(qry).all()
    
    return response

@app.patch("/maintenance/edit-status/{maintenance_id}", dependencies=[Depends(read_users_me)],response_model=MaintenanceBillRead,  response_model_exclude={"labor_cost", "parts_cost", "total_amount"})
async def edit_maintenance_issue_status(
    session: SessionDep,
    maintenance_id: UUID,
    status_change: EditMaintenanceStatus
):
    maintenance_qry = select(MaintenanceBill).where(MaintenanceBill.id == maintenance_id).options(selectinload(MaintenanceBill.house), selectinload(MaintenanceBill.tenant))
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

@app.post("/maintenance/generate/", dependencies=[Depends(read_users_me)], response_model=MaintenanceBillRead,  response_model_exclude={"labor_cost", "parts_cost", "total_amount"})
async def generate_maintenance_request(
    session: SessionDep,
    new_bill: MaintenanceBillBase
):
    bill = new_bill.model_dump()
    qry = select(Tenant).where(Tenant.hse == bill["hse_id"])
    tenant = session.exec(qry).first()
    if tenant:
        bill["tenant_id"] = tenant.id
    
    db_bill = MaintenanceBill(**bill)
    session.add(db_bill)
    session.commit()
    session.refresh(db_bill)
    
    bill_qry = select(MaintenanceBill).where(MaintenanceBill.id == db_bill.id).options(selectinload(MaintenanceBill.house), selectinload(MaintenanceBill.tenant))
    
    response = session.exec(bill_qry).first()
    
    return response

@app.post("/broadcast/send", dependencies=[Depends(read_users_me)], response_model=Broadcast)
async def send_broadcast_to_user(
    session: SessionDep,
    broadcast_detail: BroadcastBase
):
    bc = broadcast_detail.model_validate_json()
    if not bc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incomplete broadcast")

    tenants = bc.recepient
    for tenant in tenants:
        qry = select(Tenant).where(Tenant.id == tenant)
        et = session.exec(qry).first()
        if not et:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant Not found")
        # wa.send_message(
        #     to=et.tel,
        #     text=bc.message
        # )
        
        print(bc.message)
        print(f"Message sent to {et.name}")
        
    
    broadcast = Broadcast(broadcast_detail)
    
    session.add(broadcast)
    session.commit()
    session.refresh(broadcast)
    
    return broadcast