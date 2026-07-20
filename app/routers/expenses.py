# app/routers/expenses.py
from fastapi import APIRouter, Depends, Form, File, UploadFile
from typing import Annotated, List, Optional
from uuid import UUID
from datetime import datetime

from app.core.database import SessionDep
from app.core.roles import require_expense_managers
from app.models.user import User
from app.schemas.expense import (
    ExpenseRead,
    ExpenseUpdate,
    ExpenseCategory,
    ExpenseStatus,
    ExpensePaymentMethod,
    ExpenseSummary,
)
from app.services.expense_service import ExpenseService

router = APIRouter(
    prefix="/expenses",
    tags=["Expenses"],
    dependencies=[Depends(require_expense_managers)],
)


@router.post("/create", response_model=ExpenseRead)
async def create_expense(
    current_user: Annotated[User, Depends(require_expense_managers)],
    session: SessionDep,
    property_id: UUID = Form(...),
    category: ExpenseCategory = Form(ExpenseCategory.OTHER),
    description: str = Form(..., description="What this expense was for"),
    amount: float = Form(...),
    status: ExpenseStatus = Form(ExpenseStatus.OUTSTANDING),
    house_id: Optional[UUID] = Form(None),
    date_incurred: Optional[datetime] = Form(None),
    date_paid: Optional[datetime] = Form(None),
    payment_method: Optional[ExpensePaymentMethod] = Form(None),
    mpesa_message: Optional[str] = Form(None, description="Paste the raw M-Pesa confirmation SMS, optional"),
    photo: Optional[UploadFile] = File(None, description="Receipt / proof-of-payment photo, optional"),
):
    """
    Log an expense against a property (or a specific unit within it).
    Works for both an expense you're logging as already PAID (attach a
    photo and/or paste the M-Pesa confirmation text) and one that's still
    OUTSTANDING, to be marked paid later.
    """
    return await ExpenseService.create_expense(
        session, current_user, property_id, house_id, category, description, amount,
        status, date_incurred, date_paid, payment_method, mpesa_message, photo,
    )


@router.get("/property/{property_id}", response_model=List[ExpenseRead])
async def list_property_expenses(
    property_id: UUID,
    current_user: Annotated[User, Depends(require_expense_managers)],
    session: SessionDep,
    status_filter: Optional[ExpenseStatus] = None,
    category_filter: Optional[ExpenseCategory] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    return ExpenseService.list_for_property(session, current_user, property_id, status_filter, category_filter, date_from, date_to)


@router.get("/property/{property_id}/summary", response_model=ExpenseSummary)
async def get_property_expense_summary(
    property_id: UUID,
    current_user: Annotated[User, Depends(require_expense_managers)],
    session: SessionDep,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    return ExpenseService.summarize(session, current_user, property_id, date_from, date_to)


@router.get("/{expense_id}", response_model=ExpenseRead)
async def get_expense(
    expense_id: UUID,
    current_user: Annotated[User, Depends(require_expense_managers)],
    session: SessionDep,
):
    return ExpenseService.get_owned_expense(session, current_user, expense_id)


@router.patch("/{expense_id}", response_model=ExpenseRead)
async def update_expense(
    expense_id: UUID,
    current_user: Annotated[User, Depends(require_expense_managers)],
    session: SessionDep,
    category: Optional[ExpenseCategory] = Form(None),
    description: Optional[str] = Form(None),
    amount: Optional[float] = Form(None),
    status: Optional[ExpenseStatus] = Form(None),
    house_id: Optional[UUID] = Form(None),
    date_paid: Optional[datetime] = Form(None),
    payment_method: Optional[ExpensePaymentMethod] = Form(None),
    mpesa_message: Optional[str] = Form(None),
    mpesa_code: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
):
    """Edit expense details, mark it paid, or attach/replace the receipt photo."""
    expense = ExpenseService.get_owned_expense(session, current_user, expense_id)
    payload = ExpenseUpdate(
        category=category, description=description, amount=amount, status=status,
        house_id=house_id, date_paid=date_paid, payment_method=payment_method,
        mpesa_message=mpesa_message, mpesa_code=mpesa_code,
    )
    return await ExpenseService.update_expense(session, expense, payload, photo)


@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: UUID,
    current_user: Annotated[User, Depends(require_expense_managers)],
    session: SessionDep,
):
    expense = ExpenseService.get_owned_expense(session, current_user, expense_id)
    ExpenseService.delete_expense(session, expense)
    return {"message": "Expense deleted"}
