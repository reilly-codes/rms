from datetime import datetime
from uuid import UUID
from typing import Optional
from sqlmodel import Session, select
from fastapi import HTTPException, status, UploadFile

from app.models.expense import Expense
from app.models.property import Property
from app.models.user import User
from app.schemas.expense import (
    ExpenseCategory,
    ExpenseStatus,
    ExpensePaymentMethod,
    ExpenseUpdate,
    ExpenseSummary,
    ExpenseSummaryByCategory,
)
from app.services.access_control import verify_property_access
from app.services.mpesa_service import MpesaService
from app.core.media import save_upload_file, delete_upload_file


class ExpenseService:

    @staticmethod
    async def create_expense(
        session: Session,
        current_user: User,
        property_id: UUID,
        house_id: Optional[UUID],
        category: ExpenseCategory,
        description: str,
        amount: float,
        status_: ExpenseStatus,
        date_incurred: Optional[datetime],
        date_paid: Optional[datetime],
        payment_method: Optional[ExpensePaymentMethod],
        mpesa_message: Optional[str],
        photo: Optional[UploadFile],
    ) -> Expense:
        prop = verify_property_access(session, current_user, property_id)

        if house_id:
            from app.models.house import House
            house = session.get(House, house_id)
            if not house or house.property_id != property_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That unit does not belong to this property")

        mpesa_code = None
        parsed_amount = None
        parsed_date = None
        if mpesa_message:
            parsed = MpesaService.parse_mpesa_sms(mpesa_message)
            mpesa_code = parsed.get("mpesa_code")
            parsed_amount = parsed.get("amount")
            parsed_date = parsed.get("date")
            # If the expense is marked PAID and the person didn't type a
            # date_paid, trust the SMS timestamp over "now".
            if status_ == ExpenseStatus.PAID and not date_paid and parsed_date:
                date_paid = parsed_date

        photo_path = None
        if photo is not None:
            photo_path = await save_upload_file(photo, subdir="expenses")

        if status_ == ExpenseStatus.PAID and not date_paid:
            date_paid = datetime.now()
        if status_ == ExpenseStatus.OUTSTANDING:
            date_paid = None

        expense = Expense(
            property_id=property_id,
            house_id=house_id,
            landlord_id=prop.landlord_id,
            created_by=current_user.id,
            category=category,
            description=description,
            amount=amount if amount is not None else (parsed_amount or 0.0),
            status=status_,
            payment_method=payment_method,
            date_incurred=date_incurred or datetime.now(),
            date_paid=date_paid,
            mpesa_message=mpesa_message,
            mpesa_code=mpesa_code,
            receipt_photo_path=photo_path,
        )
        session.add(expense)
        session.commit()
        session.refresh(expense)
        return expense

    @staticmethod
    def list_for_property(session: Session, current_user: User, property_id: UUID,
                           status_filter: Optional[ExpenseStatus] = None,
                           category_filter: Optional[ExpenseCategory] = None,
                           date_from: Optional[datetime] = None,
                           date_to: Optional[datetime] = None):
        verify_property_access(session, current_user, property_id)

        query = select(Expense).where(Expense.property_id == property_id)
        if status_filter:
            query = query.where(Expense.status == status_filter)
        if category_filter:
            query = query.where(Expense.category == category_filter)
        if date_from:
            query = query.where(Expense.date_incurred >= date_from)
        if date_to:
            query = query.where(Expense.date_incurred <= date_to)
        query = query.order_by(Expense.date_incurred.desc())

        return session.exec(query).all()

    @staticmethod
    def get_owned_expense(session: Session, current_user: User, expense_id: UUID) -> Expense:
        expense = session.get(Expense, expense_id)
        if not expense:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
        verify_property_access(session, current_user, expense.property_id)
        return expense

    @staticmethod
    async def update_expense(session: Session, expense: Expense, payload: ExpenseUpdate, photo: Optional[UploadFile] = None) -> Expense:
        update_data = payload.model_dump(exclude_unset=True)

        if "mpesa_message" in update_data and update_data["mpesa_message"] and not update_data.get("mpesa_code"):
            parsed = MpesaService.parse_mpesa_sms(update_data["mpesa_message"])
            update_data.setdefault("mpesa_code", parsed.get("mpesa_code"))
            if not update_data.get("date_paid") and parsed.get("date"):
                update_data["date_paid"] = parsed["date"]

        for key, value in update_data.items():
            setattr(expense, key, value)

        if expense.status == ExpenseStatus.PAID and not expense.date_paid:
            expense.date_paid = datetime.now()
        if expense.status == ExpenseStatus.OUTSTANDING:
            expense.date_paid = None

        if photo is not None:
            delete_upload_file(expense.receipt_photo_path)
            expense.receipt_photo_path = await save_upload_file(photo, subdir="expenses")

        expense.updated_at = datetime.now()
        session.add(expense)
        session.commit()
        session.refresh(expense)
        return expense

    @staticmethod
    def delete_expense(session: Session, expense: Expense) -> None:
        delete_upload_file(expense.receipt_photo_path)
        session.delete(expense)
        session.commit()

    @staticmethod
    def summarize(session: Session, current_user: User, property_id: UUID,
                   date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> ExpenseSummary:
        expenses = ExpenseService.list_for_property(session, current_user, property_id, date_from=date_from, date_to=date_to)

        totals_by_cat: dict = {}
        total_all = total_paid = total_outstanding = 0.0

        for exp in expenses:
            total_all += exp.amount
            if exp.status == ExpenseStatus.PAID:
                total_paid += exp.amount
            else:
                total_outstanding += exp.amount

            bucket = totals_by_cat.setdefault(exp.category, {"total": 0.0, "paid": 0.0, "outstanding": 0.0})
            bucket["total"] += exp.amount
            if exp.status == ExpenseStatus.PAID:
                bucket["paid"] += exp.amount
            else:
                bucket["outstanding"] += exp.amount

        by_category = [
            ExpenseSummaryByCategory(category=cat, total=v["total"], paid=v["paid"], outstanding=v["outstanding"])
            for cat, v in totals_by_cat.items()
        ]

        return ExpenseSummary(
            property_id=property_id,
            total_expenses=total_all,
            total_paid=total_paid,
            total_outstanding=total_outstanding,
            by_category=by_category,
        )
