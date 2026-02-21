from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from pywa_async import WhatsApp, types

from app.db import SessionDep
from app.schemas.broadcast import BroadcastBase
from app.routers.users import active_user
from app.models.tenant import Tenant

router = APIRouter(
    prefix="/broadcast",
    tags=["Broadcast"],
    dependencies=[Depends(active_user)]
)

wa = WhatsApp(
    phone_id="",
    token="",
)


@router.post("/broadcast/send")
async def send_broadcast_to_user(
    session: SessionDep,
    broadcast_detail: BroadcastBase
):
    bc = broadcast_detail.model_validate_json()
    if not bc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incomplete broadcast")

    tenants = bc.recepient
    for tenant in tenants:
        qry = select(Tenant).where(Tenant.id == tenant)
        et = session.exec(qry).first()
        if not et:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant Not found")
        # wa.send_message(
        #     to=et.tel,
        #     text=bc.message
        # )
        
        print(bc.message)
        print(f"Message sent to {et.name}")
    
    return {"Message" : "Broadcast successfully sent."}