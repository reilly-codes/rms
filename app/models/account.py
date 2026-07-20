from sqlmodel import Field, Relationship
from uuid import UUID, uuid4
from datetime import datetime
from typing import List, TYPE_CHECKING

from app.schemas.account import AccountBase
if TYPE_CHECKING:
    from app.models.subscription import Subscription

class Account(AccountBase, table=True):
    """
    One Account per Landlord. This is the billing/SaaS-plan identity —
    separate from the User row so a landlord's login doesn't have to carry
    every billing concern directly, and so we have somewhere to hang
    subscription history off of.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    landlord_id: UUID = Field(foreign_key="user.id", unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    status: str = Field(default="ACTIVE", index=True)  # ACTIVE | SUSPENDED | CANCELLED

    subscriptions: List["Subscription"] = Relationship(back_populates="account")
