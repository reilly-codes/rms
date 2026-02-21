from sqlmodel import SQLModel, Field
from enum import Enum
from datetime import datetime

class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    IGNORED = "IGNORED"

class TransactionBase(SQLModel):
    transaction_reference: str = Field(unique=True)
    transaction_date: datetime 
    amount: float 
    transaction_status: TransactionStatus = Field(default=TransactionStatus.PENDING)