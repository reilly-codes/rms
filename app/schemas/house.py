from sqlmodel import SQLModel, Field
from enum import Enum

class HouseStatus(str, Enum):
    VACANT = "VACANT"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"

class HouseBase(SQLModel):
    number: str = Field(unique=True, index=True)
    rent: float
    deposit: float
    description: str
    status: HouseStatus = Field(default=HouseStatus.VACANT, index=True)