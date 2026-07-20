from sqlmodel import Field
from uuid import UUID, uuid4
from datetime import datetime

from app.schemas.mpesa import MpesaSTKRequestBase, MpesaRequestStatus

class MpesaSTKRequest(MpesaSTKRequestBase, table=True):
    """
    One row per STK push we initiate. Safaricom's result comes back
    asynchronously to /mpesa/callback/stk — this row is what lets that
    callback figure out which invoice or subscription the payment was for.
    """
    __tablename__ = "mpesa_stk_request"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    checkout_request_id: str | None = Field(default=None, index=True, unique=True)
    merchant_request_id: str | None = None
    status: MpesaRequestStatus = Field(default=MpesaRequestStatus.PENDING, index=True)
    result_desc: str | None = None
    mpesa_receipt: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None
