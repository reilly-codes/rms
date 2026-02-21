from sqlmodel import Field, Relationship
from datetime import datetime
from uuid import uuid4, UUID
from typing import Optional, TYPE_CHECKING

from app.schemas.payment import PaymentBase
if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.transaction import Transaction

class Payment(PaymentBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    transaction_id: UUID | None = Field(foreign_key="transaction.id", index=True, default=None)
    created_at: datetime = Field(default_factory=datetime.now)

    invoice: Optional["Invoice"] = Relationship(back_populates="payments")
    transaction: "Transaction" = Relationship(back_populates="payments")