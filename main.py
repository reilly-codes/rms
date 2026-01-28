from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, List
from datetime import timedelta
from sqlmodel import select
from uuid import UUID

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
    TransactionBase,
    Transaction,
    PaymentBase,
    Payment
)

from auth import (
    authenticate_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_active_user,
    get_password_hash
)

from db import (
    create_db_and_tables,
    SessionDep,
    lifespan,
)

app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://localhost:8080"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,   # Who can call this API
    allow_credentials=True,  # Allow cookies/auth headers
    allow_methods=["*"],     # Allow ALL methods (GET, POST, PUT, DELETE, OPTIONS)
    allow_headers=["*"],     # Allow ALL headers (Authorization, Content-Type)
)

@app.get("/")
def read_root():
    return {"Message" : "Hello Word!"}

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

# @app.get("/tenants/all")
# async def get_all_tenants(
#     session: SessionDep,
#     offset: int = 0,
#     limit: Annotated[int, Query(le=100)] = 100
# ) -> List[User]:
#     tenants = session.exec(select(User).where(User.role_id==2).offset(offset).limit(limit)).all()

#     return tenants

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
):
    statement = select(Tenant).join(House, Tenant.hse == House.id).join(Property, House.property_id == Property.id).where(Property.landlord_id == current_user.id) 

    tenants = session.exec(statement).all()

    return tenants

@app.get("/tenants/all/properties/{property_id}", response_model=List[Tenant])
async def get_tenants_by_property(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
):
    statement = select(Tenant).join(House, Tenant.hse == House.id).where(House.property_id == property.id)

    tenants = session.exec(statement).all()

    return tenants

@app.get("/tenants/{tenant_id}", response_model=Tenant)
async def get_single_tenant(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    tenant_id: str
):
    statement = select(Tenant).join(House, Tenant.hse == House.id).join(Property, House.property_id == Property.id).where(Property.landlord_id == current_user.id).where(Tenant.id == tenant_id)

    tenant = session.exec(statement).first()

    return tenant

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

@app.patch("/tenants/{tenat_id}/edit", response_model=Tenant)
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
def get_all_landlord_units(session: SessionDep, current_user: Annotated[User, Depends(read_users_me)]):
    statement = (
        select(House)
        .join(Property, House.property_id == Property.id)
        .where(Property.landlord_id == current_user.id)
    )
    units = session.exec(statement).all()
    return units


@app.get("/invoices/{hse_id}", response_model=List[Invoice])
def get_all_invoices_by_hse(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    hse_id: str,
):
    statement = select(Invoice).join(Property, House.property_id == Property.id).join(House, Property.landlord_id == current_user.id).where(House.id == hse_id)

    invoices = session.exec(statement).all()

    return invoices

@app.get("invoices/tenant/{tenant_id}", response_model=List[Invoice])
async def get_all_invoices_by_tenant(
    session: SessionDep,
    current_user: Annotated[User, Depends(read_users_me)],
    tenant_id: str
):
    statement = select(Invoice).join(Tenant, Invoice.hse_id == Tenant.hse).join(House, Property.landlord_id == current_user.id).where(Invoice.tenant_id == tenant_id)

    invoices = session.exec(statement).all()

    return invoices

@app.get("invoices/{invoice_id}", response_model=Invoice)
async def show_single_invoice(
    session: SessionDep,
    invoice_id: str
):
    statement = select(Invoice).where(Invoice.id == invoice_id)

    invoice = session.exec(statement).first()

    return invoice

# @app.post("invoice/generate", response_model=List[Invoice])
# async def generate_tenant_invoices(
#     session: SessionDep,
#     invoice_create: InvoiceBase
# ):
    