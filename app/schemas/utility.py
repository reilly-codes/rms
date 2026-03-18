from enum import Enum
from sqlmodel import SQLModel, Field
from datetime import datetime
from uuid import UUID

class BillType(str, Enum):
    WATER = "WATER"
    ELECTRICITY = "ELECTRICITY"
    OTHER = "OTHER"

class UtilityBillBase(SQLModel):
    date_gen: datetime = Field(default_factory=datetime.now)
    bill_type: BillType
    amount : float
    
class UtilityBillRead(UtilityBillBase):
    id: UUID