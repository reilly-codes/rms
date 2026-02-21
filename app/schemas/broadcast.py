from sqlmodel import SQLModel, Field
from enum import Enum
from typing import List
from uuid import UUID

class MessageType(str, Enum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"

class BroadcastBase(SQLModel):
    message: str
    message_type: MessageType = Field(default=MessageType.WHATSAPP)
    recepient: List[UUID]