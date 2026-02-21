from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from typing import List, Annotated
from uuid import UUID

from app.db import SessionDep
from app.models.tenant import Tenant
from app.models.house import House
from app.models.property import Property
from app.models.user import User
from app.schemas.tenant import TenantBase
from app.routers.users import active_user
from app.routers.properties import get_individual_property

router = APIRouter(
    prefix="/tenants",
    tags=["Tenants"],
    dependencies=[Depends(active_user)]
)

@router.get("/all", response_model=List[Tenant])
async def get_all_tenants(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    property_id: UUID | None = None
):
    statement = select(Tenant).join(House, Tenant.hse == House.id).join(Property, House.property_id == Property.id).where(Property.landlord_id == current_user.id)
    
    if property_id:
        statement = statement.where(House.property_id == property_id)

    tenants = session.exec(statement).all()

    return tenants

@router.get("/{tenant_id}", response_model=Tenant)
async def get_single_tenant(
    session: SessionDep,
    current_user: Annotated[User, Depends(active_user)],
    tenant_id: UUID
):
    statement = select(Tenant).join(House, Tenant.hse == House.id).join(Property, House.property_id == Property.id).where(Property.landlord_id == current_user.id).where(Tenant.id == tenant_id)

    tenant = session.exec(statement).first()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant

@router.post("/create/properties/{property_id}", response_model=Tenant)
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

@router.patch("/{tenant_id}/edit", response_model=Tenant)
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