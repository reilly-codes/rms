from sqlmodel import Field, Relationship
from uuid import UUID, uuid4
from datetime import datetime
from typing import TYPE_CHECKING

from app.schemas.subscription import SubscriptionBase, SubscriptionStatus
if TYPE_CHECKING:
    from app.models.account import Account

class Subscription(SubscriptionBase, table=True):
    """
    Historical row-per-period. Only one row per account should have
    is_current=True at a time; renewing/upgrading flips the old row's
    is_current to False and inserts a new one, so billing history survives.

    Business rules (mirrors the pattern already proven on ONA24):
    - billing_day is fixed at first onboarding and never moves
    - grace_period_ends_at is only ever set on the very first period
      (onboarding). Renewals get no grace — miss a renewal and you go
      straight from ACTIVE to SUSPENDED once current_period_end passes.
    - suspended_at is stamped the moment a subscription flips to SUSPENDED,
      and is what the delete-after-N-days trigger measures against.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="account.id", index=True)

    status: SubscriptionStatus = Field(default=SubscriptionStatus.TRIALING, index=True)
    billing_day: int  # day-of-month (1-28) this subscription bills on, fixed at onboarding

    current_period_start: datetime = Field(default_factory=datetime.now)
    current_period_end: datetime
    grace_period_ends_at: datetime | None = None
    suspended_at: datetime | None = None

    is_current: bool = Field(default=True, index=True)
    last_payment_ref: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None

    account: "Account" = Relationship(back_populates="subscriptions")
