from sqlmodel import Field, Relationship
from uuid import uuid4, UUID
from typing import List, TYPE_CHECKING

from app.schemas.invoice import InvoiceBase
if TYPE_CHECKING:
    from app.models.house import House
    from app.models.tenant import Tenant
    from app.models.utility import UtilityBill
    from app.models.payment import Payment

class Invoice(InvoiceBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    comments: str | None

    payments: List["Payment"] = Relationship(back_populates="invoice")
    utilities: List["UtilityBill"] = Relationship(back_populates="invoice")
    house: "House" = Relationship()
    tenant: "Tenant" = Relationship()