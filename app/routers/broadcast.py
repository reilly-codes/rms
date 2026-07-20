from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select, col
from typing import Annotated
from pywa_async import WhatsApp

from app.core.database import SessionDep
from app.schemas.broadcast import BroadcastBase
from app.routers.users import active_user
from app.models.tenant import Tenant

router = APIRouter(
    prefix="/broadcast",
    tags=["Broadcast"],
    dependencies=[Depends(active_user)]
)

# Keep the client instance ready
# In production, pull these keys from your app's core configuration settings
wa = WhatsApp(
    phone_id="your_phone_id",
    token="your_meta_access_token",
)


@router.post("/send", status_code=status.HTTP_200_OK)
async def send_broadcast_to_user(
    session: SessionDep,
    broadcast_detail: BroadcastBase
):
    if not broadcast_detail or not broadcast_detail.recepient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Incomplete broadcast or recipient list is empty"
        )

    # 1. Query all targeted tenants in a single batch operation 
    # (Much faster than executing SQL queries repeatedly inside a loop)
    stmt = select(Tenant).where(col(Tenant.id).in_(broadcast_detail.recepient))
    tenants = session.exec(stmt).all()

    if not tenants:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="None of the specified recipients could be found"
        )

    # 2. Loop through the resolved models and dispatch asynchronously
    sent_count = 0
    failed_recipients = []

    for tenant in tenants:
        if not tenant.tel:
            failed_recipients.append(tenant.name)
            continue
            
        try:
            # Crucial: Since you're using pywa_async, 'await' is mandatory!
            await wa.send_message(
                to=tenant.tel,
                text=broadcast_detail.message
            )
            sent_count += 1
            print(f"Successfully broadcasted to {tenant.name} ({tenant.tel})")
            
        except Exception as e:
            print(f"Failed to send message to {tenant.name}: {e}")
            failed_recipients.append(tenant.name)

    # 3. Report back detailed transmission feedback
    return {
        "status": "completed",
        "total_targets": len(broadcast_detail.recepient),
        "successfully_sent": sent_count,
        "failures": failed_recipients if failed_recipients else None
    }