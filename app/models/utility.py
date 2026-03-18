from sqlmodel import Field, Relationship
from uuid import uuid4, UUID
from typing import TYPE_CHECKING

from app.schemas.utility import UtilityBillBase
if TYPE_CHECKING:
    from app.models.invoice import Invoice

class UtilityBill(UtilityBillBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(foreign_key="invoice.id", index=True)

    invoice: "Invoice" = Relationship(
        back_populates="utilities",
        cascade_delete=True,
    )