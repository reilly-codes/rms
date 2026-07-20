"""
Account/Subscription lifecycle.

Business rules (same pattern already validated on ONA24):
- billing_day is fixed the day the landlord onboards and never changes.
- The very first period gets a grace window after current_period_end before
  anything bad happens (SUBSCRIPTION_ONBOARDING_GRACE_DAYS). Renewals get
  none — miss a renewal and the very next billing check suspends you.
- A subscription that's been SUSPENDED for longer than
  SUBSCRIPTION_SUSPEND_AFTER_DAYS... no wait: suspension itself happens
  after non-payment; then if it stays SUSPENDED for
  SUBSCRIPTION_DELETE_AFTER_SUSPENDED_DAYS more days, the landlord's whole
  account (properties, tenants, everything — via the existing cascade
  delete service) is actually deleted. That's the "suspend-then-delete"
  trigger becoming real.

run_subscription_billing_check() is meant to be invoked by a daily cron
(see app/scripts/run_subscription_check.py) exactly like ONA24's
expire_subscriptions cron.
"""
from datetime import datetime, timedelta
from uuid import UUID
from sqlmodel import Session, select
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.user import User
from app.models.account import Account
from app.models.subscription import Subscription
from app.schemas.account import AccountType
from app.schemas.subscription import SubscriptionPlan, SubscriptionStatus
from app.services.cascade_delete import delete_landlord_cascade


class SubscriptionService:

    # --- Onboarding --------------------------------------------------

    @staticmethod
    def create_account_with_trial(session: Session, landlord: User, account_type: AccountType = AccountType.INDIVIDUAL) -> Account:
        """Called right after a landlord self-registers. Starts them on a
        trial so the app is usable immediately, with billing_day fixed to
        today from here on out."""
        account = Account(landlord_id=landlord.id, account_type=account_type)
        session.add(account)
        session.flush()

        now = datetime.now()
        period_end = now + timedelta(days=settings.SUBSCRIPTION_TRIAL_DAYS)

        subscription = Subscription(
            account_id=account.id,
            plan=SubscriptionPlan.BASIC,
            amount=0.0,
            status=SubscriptionStatus.TRIALING,
            billing_day=now.day,
            current_period_start=now,
            current_period_end=period_end,
            grace_period_ends_at=period_end + timedelta(days=settings.SUBSCRIPTION_ONBOARDING_GRACE_DAYS),
            is_current=True,
        )
        session.add(subscription)
        session.commit()
        session.refresh(account)
        return account

    # --- Plan gating ---------------------------------------------------

    @staticmethod
    def get_current_subscription(session: Session, landlord_id: UUID) -> Subscription | None:
        account = session.exec(select(Account).where(Account.landlord_id == landlord_id)).first()
        if not account:
            return None
        return session.exec(
            select(Subscription)
            .where(Subscription.account_id == account.id)
            .where(Subscription.is_current == True)  # noqa: E712
        ).first()

    @staticmethod
    def require_property_management_plan(session: Session, landlord: User) -> Subscription:
        """Gate for anything Property-Manager-related: creating PM accounts,
        or granting PropertyAssignments to them. Raises 402/403 if the
        landlord's plan doesn't cover it."""
        sub = SubscriptionService.get_current_subscription(session, landlord.id)
        if not sub:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="No active subscription found")

        if sub.status == SubscriptionStatus.SUSPENDED:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Your subscription is suspended. Please renew to continue.")

        if sub.plan != SubscriptionPlan.PROPERTY_MANAGEMENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Property Manager accounts require the Property Management plan. Upgrade your subscription to unlock this.",
            )
        return sub

    @staticmethod
    def require_active_subscription(session: Session, landlord: User) -> Subscription:
        sub = SubscriptionService.get_current_subscription(session, landlord.id)
        if not sub or sub.status == SubscriptionStatus.SUSPENDED:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Your subscription is suspended. Please renew to continue.")
        return sub

    # --- Payment application --------------------------------------------

    @staticmethod
    def activate_subscription_from_payment(session: Session, account_id: UUID, amount: float, reference: str, plan: SubscriptionPlan | None = None) -> Subscription:
        """Called once a subscription payment is confirmed (M-Pesa STK
        callback, manual entry, or bank-statement reconciliation match).
        Renewals get NO grace period — that's onboarding-only."""
        current = session.exec(
            select(Subscription)
            .where(Subscription.account_id == account_id)
            .where(Subscription.is_current == True)  # noqa: E712
        ).first()

        now = datetime.now()
        billing_day = current.billing_day if current else now.day
        new_plan = plan or (current.plan if current else SubscriptionPlan.BASIC)

        if current:
            current.is_current = False
            session.add(current)

        new_period_end = now + timedelta(days=settings.SUBSCRIPTION_PERIOD_DAYS)
        new_sub = Subscription(
            account_id=account_id,
            plan=new_plan,
            amount=amount,
            status=SubscriptionStatus.ACTIVE,
            billing_day=billing_day,
            current_period_start=now,
            current_period_end=new_period_end,
            grace_period_ends_at=None,  # no grace on renewals
            is_current=True,
            last_payment_ref=reference,
        )
        session.add(new_sub)

        account = session.get(Account, account_id)
        if account and account.status == "SUSPENDED":
            account.status = "ACTIVE"
            session.add(account)

        session.commit()
        session.refresh(new_sub)
        return new_sub

    @staticmethod
    def record_manual_subscription_payment(session: Session, landlord: User, amount: float, reference: str, plan: SubscriptionPlan | None = None) -> Subscription:
        account = session.exec(select(Account).where(Account.landlord_id == landlord.id)).first()
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found for this landlord")
        return SubscriptionService.activate_subscription_from_payment(session, account.id, amount, reference, plan)

    @staticmethod
    def change_plan(session: Session, landlord: User, plan: SubscriptionPlan, amount: float) -> Subscription:
        """Upgrades/downgrades without requiring a fresh payment right away
        (e.g. admin override, or plan change effective next renewal)."""
        sub = SubscriptionService.get_current_subscription(session, landlord.id)
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found")
        sub.plan = plan
        sub.amount = amount
        sub.updated_at = datetime.now()
        session.add(sub)
        session.commit()
        session.refresh(sub)
        return sub

    # --- The suspend-then-delete billing trigger ------------------------

    @staticmethod
    def run_subscription_billing_check(session: Session) -> dict:
        """
        Meant to run daily. For every is_current subscription:
          1. TRIALING/ACTIVE past current_period_end and still inside its
             (onboarding-only) grace window -> GRACE.
          2. Past current_period_end with no grace window, or past the
             grace window -> SUSPENDED (account.status = SUSPENDED too).
          3. Already SUSPENDED for longer than
             SUBSCRIPTION_DELETE_AFTER_SUSPENDED_DAYS since suspended_at ->
             the landlord's entire account (properties, tenants, invoices,
             the works) is cascade-deleted. This is intentionally
             destructive and is the "real" trigger — call this from a cron,
             not from a request handler a user can trigger accidentally.
        """
        now = datetime.now()
        moved_to_grace = 0
        moved_to_suspended = 0
        deleted_accounts = 0

        current_subs = session.exec(
            select(Subscription).where(Subscription.is_current == True)  # noqa: E712
        ).all()

        for sub in current_subs:
            if sub.status in (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE):
                if now <= sub.current_period_end:
                    continue

                if sub.grace_period_ends_at and now <= sub.grace_period_ends_at:
                    sub.status = SubscriptionStatus.GRACE
                    session.add(sub)
                    moved_to_grace += 1
                    continue

                sub.status = SubscriptionStatus.SUSPENDED
                sub.suspended_at = now
                session.add(sub)
                account = session.get(Account, sub.account_id)
                if account:
                    account.status = "SUSPENDED"
                    session.add(account)
                moved_to_suspended += 1
                continue

            if sub.status == SubscriptionStatus.GRACE:
                if sub.grace_period_ends_at and now > sub.grace_period_ends_at:
                    sub.status = SubscriptionStatus.SUSPENDED
                    sub.suspended_at = now
                    session.add(sub)
                    account = session.get(Account, sub.account_id)
                    if account:
                        account.status = "SUSPENDED"
                        session.add(account)
                    moved_to_suspended += 1
                continue

            if sub.status == SubscriptionStatus.SUSPENDED and sub.suspended_at:
                delete_after = sub.suspended_at + timedelta(days=settings.SUBSCRIPTION_DELETE_AFTER_SUSPENDED_DAYS)
                if now > delete_after:
                    account = session.get(Account, sub.account_id)
                    if account:
                        landlord = session.get(User, account.landlord_id)
                        if landlord:
                            # delete_landlord_cascade handles Account +
                            # every Subscription row too (no DB-level
                            # ON DELETE CASCADE anywhere in this schema).
                            delete_landlord_cascade(session, landlord)
                            deleted_accounts += 1

        session.commit()
        return {
            "checked": len(current_subs),
            "moved_to_grace": moved_to_grace,
            "moved_to_suspended": moved_to_suspended,
            "deleted_accounts": deleted_accounts,
        }
