# app/routers/subscriptions.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from sqlmodel import select

from app.core.database import SessionDep
from app.core.roles import require_landlord
from app.models.user import User
from app.models.account import Account
from app.schemas.account import AccountRead, AccountUpdate
from app.schemas.subscription import (
    SubscriptionRead,
    SubscriptionChangePlan,
    ManualSubscriptionPayment,
)
from app.services.subscription_service import SubscriptionService

router = APIRouter(
    prefix="/account",
    tags=["Account & Subscription"],
    dependencies=[Depends(require_landlord)],
)


@router.get("/", response_model=AccountRead)
async def get_my_account(
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    account = session.exec(select(Account).where(Account.landlord_id == current_landlord.id)).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found — this is unexpected for an existing landlord login")
    return account


@router.patch("/", response_model=AccountRead)
async def update_my_account(
    payload: AccountUpdate,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    account = session.exec(select(Account).where(Account.landlord_id == current_landlord.id)).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, key, value)

    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.get("/subscription", response_model=SubscriptionRead)
async def get_my_subscription(
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    sub = SubscriptionService.get_current_subscription(session, current_landlord.id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subscription found")
    return sub


@router.post("/subscription/change-plan", response_model=SubscriptionRead)
async def change_plan(
    payload: SubscriptionChangePlan,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    return SubscriptionService.change_plan(session, current_landlord, payload.plan, payload.amount)


@router.post("/subscription/manual-payment", response_model=SubscriptionRead)
async def record_manual_payment(
    payload: ManualSubscriptionPayment,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    """For offline payments (bank transfer, till confirmed manually, etc.)
    that won't come through the M-Pesa STK callback or bank-statement
    reconciliation."""
    return SubscriptionService.record_manual_subscription_payment(
        session, current_landlord, payload.amount, payload.reference, plan=None
    )
