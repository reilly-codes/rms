from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
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
from app.schemas.tenant import TenantBase, TenantCreate, TenantPrint
from app.routers.users import active_user
from app.routers.properties import get_individual_property
from app.auth import get_password_hash
from app.services.cascade_delete import delete_tenant_full_cascade
from sqlalchemy.exc import IntegrityError

router = APIRouter(
    prefix="/tenants",
    tags=["Tenants"],
    dependencies=[Depends(active_user)]
)

@router.post("/create/properties/{property_id}", response_model=TenantPrint)
async def create_tenant(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
    newTenant: TenantCreate,
):
    
    selected_hse = session.get(House, newTenant.hse)

    if not selected_hse :
        raise HTTPException(status_code=404, detail="Selected house is not found")
    
    if selected_hse.property_id != property.id:
        raise HTTPException(status_code=400, detail="This unit is not available in this property")
    
    if selected_hse.status != "VACANT":
        raise HTTPException(status_code=400, detail="Selected Unit is unavailable")
    
    # dbTenant = Tenant.model_validate(newTenant)
    # session.add(dbTenant)
    # selected_hse.status = "OCCUPIED"
    # session.add(selected_hse)
    # session.commit()
    # session.refresh(dbTenant)
    try:
        input_data = newTenant.model_dump()

        tenant_user = User(
            name=input_data["name"],
            email=input_data["email"],
            tel=input_data["tel"],
            role_id=2,
            landlord_id=property.landlord_id,
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
        
        session.refresh(unit_tenant_connection)
        session.refresh(selected_hse)
        session.refresh(db_tenant)
        
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=400, detail="A tenant or account with this email already exists")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=(str(e)))

    return db_tenant


@router.get("/all", response_model=List[TenantPrint])
async def get_all_tenants(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    property_id: UUID | None = None
):
    # old db schema query
    # statement = select(Tenant).join(House, Tenant.hse == House.id).join(Property, House.property_id == Property.id).where(Property.landlord_id == current_user.id)
    
    # new db schema query
    statement = select(Tenant).join(TenantUnit).join(House, House.id == TenantUnit.hse_id).join(Property, Property.id == House.property_id).where(Property.landlord_id == current_user.id)
    
    if property_id:
        statement = statement.where(House.property_id == property_id)
        
    statement = statement.options(selectinload(Tenant.houses).selectinload(TenantUnit.house))

    tenants = session.exec(statement).all()

    return tenants

@router.get("/me", response_model=dict)
async def get_current_tenant(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
):
    """Get the currently logged-in tenant's record with unit details."""
    statement = select(Tenant).where(Tenant.user_id == current_user.id)
    tenant = session.exec(statement).first()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant record not found")
    
    # Get the tenant's active unit and rent info
    unit_statement = select(TenantUnit, House).join(House).where(
        TenantUnit.tenant_id == tenant.id
    ).where(
        TenantUnit.rent_end == None  # Only active tenancy
    )
    unit_row = session.exec(unit_statement).first()
    
    unit_number = "N/A"
    monthly_rent = None
    if unit_row:
        tenant_unit, house = unit_row
        unit_number = house.number
        monthly_rent = house.rent
    
    return {
        "id": tenant.id,
        "name": current_user.name,
        "email": current_user.email,
        "tel": current_user.tel,
        "role_id": current_user.role_id,
        "national_id": tenant.national_id,
        "status": tenant.status,
        "wallet_balance": tenant.wallet_balance,
        "created_at": tenant.created_at,
        "user_id": tenant.user_id,
        "unit_number": unit_number,
        "monthly_rent": monthly_rent,
        "houses": [],
    }   

@router.get("/{tenant_id}", response_model=Tenant)
async def get_single_tenant(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    tenant_id: UUID
):
    statement = select(Tenant).join(TenantUnit, TenantUnit.tenant_id == Tenant.id).join(House, House.id == TenantUnit.hse_id).join(Property, Property.id == House.property_id).where(Property.landlord_id == current_user.id).where(Tenant.id == tenant_id)

    tenant = session.exec(statement).first()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant



# improve logic for move out notice and end tenant Unit
@router.patch("/{tenant_id}/edit", response_model=TenantPrint)
async def edit_tenant_details(
    session: SessionDep,
    tenant: Annotated[Tenant, Depends(get_single_tenant)],
    tenantUpdate: TenantBase
):
    tenantData = tenantUpdate.model_dump(exclude_unset=True)

    for key,value in tenantData.items():
        setattr(tenant, key, value)

    # Keep the linked login account's identity fields in sync — the tenant's
    # email specifically is also their login username, so letting it drift
    # from the business record would silently break their portal access.
    if tenant.user_id:
        linked_user = session.get(User, tenant.user_id)
        if linked_user:
            for key in ("name", "email", "tel"):
                if key in tenantData:
                    setattr(linked_user, key, tenantData[key])
            session.add(linked_user)
        
    if tenant.status == "VACATED":
        qry = select(TenantUnit).where(TenantUnit.tenant_id == tenant.id)
        tu = session.exec(qry).first()
        tu.rent_end = datetime.now()
        session.add(tu)
        
    elif tenant.status == "MOVING OUT":
        qry = select(TenantUnit).where(TenantUnit.tenant_id == tenant.id)
        tu = session.exec(qry).first()
        tu.rent_end = datetime.now() + timedelta(days=30)
        session.add(tu)
        
        
        

    session.add(tenant)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=400, detail="Another account already uses this email")
    session.refresh(tenant)

    return tenant

@router.delete("/{tenant_id}")
async def delete_tenant(
    session: SessionDep,
    tenant: Annotated[Tenant, Depends(get_single_tenant)],
):
    # Vacate the house(s) this tenant occupied before removing them, so the
    # unit becomes bookable again rather than being left stuck OCCUPIED with
    # no tenant attached.
    units = session.exec(select(TenantUnit).where(TenantUnit.tenant_id == tenant.id)).all()
    for unit in units:
        house = session.get(House, unit.hse_id)
        if house:
            house.status = "VACANT"
            session.add(house)

    delete_tenant_full_cascade(session, tenant)
    session.commit()

    return {"message": "Tenant and all associated records deleted successfully"}