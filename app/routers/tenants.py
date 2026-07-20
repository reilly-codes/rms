# app/routers/tenants.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlalchemy.orm import selectinload
from typing import List, Annotated
from uuid import UUID

from app.core.database import SessionDep
from app.core.roles import require_landlord, require_tenant
from app.services.auth_service import get_current_active_user

from app.models.tenant import Tenant
from app.models.house import House
from app.models.tenant_unit import TenantUnit
from app.models.property import Property
from app.models.user import User
from app.schemas.tenant import TenantBase, TenantCreate, TenantPrint

from app.routers.properties import get_individual_property
from app.services.tenant_service import TenantService

router = APIRouter(
    prefix="/tenants",
    tags=["Tenants"],
    dependencies=[Depends(get_current_active_user)]
)


@router.post("/create/properties/{property_id}", response_model=TenantPrint, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    session: SessionDep,
    property: Annotated[Property, Depends(get_individual_property)],
    current_user: Annotated[User, Depends(require_landlord)],  # Ensure only Landlords can onboard tenants
    newTenant: TenantCreate,
):
    """Create a tenant account, register login credentials, and assign them to an empty unit."""
    return await TenantService.create_tenant_account(
        session=session, 
        property_landlord_id=property.landlord_id, 
        property_id=property.id, 
        new_tenant=newTenant
    )


@router.get("/all", response_model=List[TenantPrint])
async def get_all_tenants(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_landlord)],
    property_id: UUID | None = None
):
    """Retrieve all tenants registered on properties owned by this landlord."""
    statement = (
        select(Tenant)
        .join(TenantUnit)
        .join(House, House.id == TenantUnit.hse_id)
        .join(Property, Property.id == House.property_id)
        .where(Property.landlord_id == current_user.id)
    )
    
    if property_id:
        statement = statement.where(House.property_id == property_id)
        
    statement = statement.options(selectinload(Tenant.houses).selectinload(TenantUnit.house))
    return session.exec(statement).all()


@router.get("/me", response_model=dict)
async def get_current_tenant(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_tenant)],
):
    """Retrieve profile details and active unit layout for the logged-in tenant."""
    statement = select(Tenant).where(Tenant.user_id == current_user.id)
    tenant = session.exec(statement).first()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant record not found")
    
    unit_statement = (
        select(TenantUnit, House)
        .join(House)
        .where(TenantUnit.tenant_id == tenant.id)
        .where(TenantUnit.rent_end == None)
    )
    unit_row = session.exec(unit_statement).first()
    
    unit_number = "N/A"
    monthly_rent = None
    if unit_row:
        _, house = unit_row
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
    current_user: Annotated[User, Depends(require_landlord)],
    tenant_id: UUID
):
    """Retrieve detailed tenant record, securely scoped to verify landlord ownership."""
    statement = (
        select(Tenant)
        .join(TenantUnit, TenantUnit.tenant_id == Tenant.id)
        .join(House, House.id == TenantUnit.hse_id)
        .join(Property, Property.id == House.property_id)
        .where(Property.landlord_id == current_user.id)
        .where(Tenant.id == tenant_id)
    )
    tenant = session.exec(statement).first()
    
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.patch("/{tenant_id}/edit", response_model=TenantPrint)
async def edit_tenant_details(
    session: SessionDep,
    tenant: Annotated[Tenant, Depends(get_single_tenant)],  # Enforces landlord ownership checks
    tenantUpdate: TenantBase
):
    """Update tenant personal profile fields and keep active login credentials in sync."""
    return await TenantService.update_tenant_account(session, tenant, tenantUpdate)


@router.delete("/{tenant_id}", status_code=status.HTTP_200_OK)
async def delete_tenant(
    session: SessionDep,
    tenant: Annotated[Tenant, Depends(get_single_tenant)],  # Enforces landlord ownership checks
):
    """Completely cascade delete a tenant profile, resetting their assigned housing units back to vacant."""
    await TenantService.delete_tenant_account(session, tenant)
    return {"message": "Tenant and all associated records deleted successfully"}