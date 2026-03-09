from sqlmodel import Field, Relationship
from uuid import uuid4, UUID
from datetime import datetime
from typing import List, TYPE_CHECKING

from app.schemas.tenant import TenantBase
if TYPE_CHECKING:
    from app.models.tenant_unit import TenantUnit


class Tenant(TenantBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    wallet_balance: float = Field(default=0.0)

    houses: List["TenantUnit"] = Relationship(back_populates="tenant")