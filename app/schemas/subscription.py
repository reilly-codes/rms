from sqlmodel import SQLModel, Field
from enum import Enum
from uuid import UUID
from datetime import datetime

class SubscriptionPlan(str, Enum):
    BASIC = "BASIC"                    # single landlord, no Property Manager role
    STANDARD = "STANDARD"              # single landlord, more units, no Property Manager role
    PROPERTY_MANAGEMENT = "PROPERTY_MANAGEMENT"  # unlocks Property Manager role + multi-landlord assignment

class SubscriptionStatus(str, Enum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    GRACE = "GRACE"           # past due, first-onboarding grace window only
    SUSPENDED = "SUSPENDED"   # access cut off, not yet deleted
    CANCELLED = "CANCELLED"

class SubscriptionBase(SQLModel):
    plan: SubscriptionPlan = Field(default=SubscriptionPlan.BASIC, index=True)
    amount: float = 0.0
    currency: str = "KES"

class SubscriptionRead(SubscriptionBase):
    id: UUID
    account_id: UUID
    status: SubscriptionStatus
    billing_day: int
    current_period_start: datetime
    current_period_end: datetime
    grace_period_ends_at: datetime | None = None
    suspended_at: datetime | None = None
    is_current: bool
    last_payment_ref: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

class SubscriptionChangePlan(SQLModel):
    plan: SubscriptionPlan
    amount: float

class ManualSubscriptionPayment(SQLModel):
    """Landlord/admin records an offline payment (bank transfer, manual M-Pesa
    till confirmation, etc.) against their subscription."""
    amount: float
    reference: str
    date_paid: datetime | None = None
