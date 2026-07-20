from sqlmodel import Field, Relationship
from typing import List, TYPE_CHECKING
from uuid import uuid4, UUID

from app.schemas.transaction import TransactionBase
if TYPE_CHECKING:
    from app.models.payment import Payment

class Transaction(TransactionBase, table=True):
    id: UUID | None = Field(primary_key=True, default_factory=uuid4)
    
    payments: List["Payment"] = Relationship(
        back_populates="transaction",
        sa_relationship_kwargs={"foreign_keys": "Payment.transaction_id"},
    )