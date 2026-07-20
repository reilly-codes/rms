# app/routers/invoices.py
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlmodel import select
from sqlalchemy.orm import selectinload
from typing import List, Annotated
from uuid import UUID

from app.core.database import SessionDep
from app.models.user import User
from app.models.invoice import Invoice
from app.models.tenant_unit import TenantUnit
from app.models.house import House
from app.models.property import Property
from app.schemas.invoice import InvoiceGenerationRequest, InvoiceRead
from app.core.roles import require_management  # Handles Landlord/Caretaker validation
from app.services.auth_service import get_current_active_user
from app.services.invoice_service import InvoiceService

router = APIRouter(
    prefix="/invoices",
    tags=["Invoices"],
    dependencies=[Depends(get_current_active_user)]  # Authenticated users can read their resources
)

@router.get("/rent/all", response_model=List[InvoiceRead])
async def get_all_invoices(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    hse_id: UUID | None = None,
    tenant_id: UUID | None = None
):
    """Retrieve rent invoices, filtered by property ownership rules."""
    statement = (
        select(Invoice)
        .join(TenantUnit, Invoice.tenant_unit_id == TenantUnit.id)
        .join(House, House.id == TenantUnit.hse_id)
        .join(Property, Property.id == House.property_id)
    )
    
    # If a Landlord/Caretaker reads, scoped to their properties. Tenants only see their own.
    if current_user.role_id in [1, 2]:  # Landlord / Caretaker
        statement = statement.where(Property.landlord_id == current_user.id)
    else:
        statement = statement.where(TenantUnit.tenant_id == current_user.id)
    
    if hse_id:
        statement = statement.where(TenantUnit.hse_id == hse_id)
    if tenant_id:
        statement = statement.where(TenantUnit.tenant_id == tenant_id)

    statement = statement.options(
        selectinload(Invoice.tenant_unit).selectinload(TenantUnit.house),
        selectinload(Invoice.tenant_unit).selectinload(TenantUnit.tenant),
        selectinload(Invoice.utilities)
    )
    return session.exec(statement).all()


@router.get("/rent/{invoice_id}", response_model=Invoice)
async def show_single_invoice(
    session: SessionDep,
    invoice_id: UUID
):
    statement = (
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(
            selectinload(Invoice.tenant_unit).selectinload(TenantUnit.house),
            selectinload(Invoice.tenant_unit).selectinload(TenantUnit.tenant),
            selectinload(Invoice.utilities)
        )
    )
    invoice = session.exec(statement).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@router.post("/generate/rent/{hse_id}", response_model=Invoice)
async def generate_tenant_rent_invoices(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_management)],
    utility_list: InvoiceGenerationRequest,
    hse_id: UUID
):
    """Generates a monthly invoice with static target due (5th) and deadline (7th) limits."""
    return await InvoiceService.create_tenant_invoice(session, hse_id, utility_list)


@router.patch("/rent/{invoice_id}/edit", response_model=Invoice)
async def edit_specific_rent_invoice(
    session: SessionDep,
    invoice_id: UUID,
    current_user: Annotated[User, Depends(require_management)],
    utility_list: InvoiceGenerationRequest
):
    """Updates custom utility charges and scales the bill amount dynamically."""
    return await InvoiceService.update_invoice(session, invoice_id, utility_list)


@router.delete("/rent/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rent_invoice(
    session: SessionDep,
    invoice_id: UUID,
    current_user: Annotated[User, Depends(require_management)]
):
    """Delete a specific invoice."""
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    session.delete(invoice)
    session.commit()
    return None


@router.post("/rent/bulk/upload")
async def bulk_upload_old_rent_invoices(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_management)],
    property_id: UUID,
    file: UploadFile = File(...)
):
    """Parse historical sheets and create structured past-due invoice lists."""
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid File format. Please upload CSV or Excel"
        )
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file.file)
            df_dict = {"CSV_Data": df}
        else:
            df_dict = pd.read_excel(file.file, sheet_name=None)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Could not read file: {str(e)}"
        )
    
    try:
        count = await InvoiceService.bulk_upload_invoices(session, property_id, df_dict)
        return {"message": "Invoices successfully created", "count": count}
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error executing raw pipeline: {str(e)}"
        )