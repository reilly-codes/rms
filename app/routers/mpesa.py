# app/routers/mpesa.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import Annotated
from datetime import datetime
from sqlmodel import select

from app.core.database import SessionDep
from app.core.roles import require_tenant, require_landlord
from app.models.user import User
from app.models.invoice import Invoice
from app.models.tenant import Tenant
from app.models.tenant_unit import TenantUnit
from app.models.house import House
from app.models.account import Account
from app.models.mpesa import MpesaSTKRequest
from app.schemas.mpesa import (
    STKPushInitiateRent,
    STKPushInitiateSubscription,
    MpesaSTKRequestRead,
    MpesaPurpose,
    MpesaRequestStatus,
)
from app.schemas.payment import PaymentBase, PaymentStatus as ModelPaymentStatus
from app.services.mpesa_service import MpesaService
from app.services.payment_service import PaymentService
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger("mpesa")

router = APIRouter(prefix="/mpesa", tags=["M-Pesa"])


@router.post("/stk-push/rent", response_model=MpesaSTKRequestRead)
async def initiate_rent_stk_push(
    payload: STKPushInitiateRent,
    current_tenant: Annotated[User, Depends(require_tenant)],
    session: SessionDep,
):
    """Tenant pays an invoice directly from the app — no need to paste an
    M-Pesa message afterwards, the callback confirms and allocates it
    automatically."""
    invoice = session.get(Invoice, payload.invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    tenant = session.exec(select(Tenant).where(Tenant.user_id == current_tenant.id)).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant profile not found")

    tu = session.get(TenantUnit, invoice.tenant_unit_id)
    if not tu or tu.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This invoice does not belong to you")

    house = session.get(House, tu.hse_id)
    account_reference = (house.number if house and house.number else (tenant.name or "RENT").replace(" ", ""))[:12]

    stk_response = MpesaService.stk_push(
        phone_number=payload.phone_number,
        amount=payload.amount,
        account_reference=account_reference,
        transaction_desc=f"Rent payment - invoice {str(invoice.id)[:8]}",
        callback_path="/mpesa/callback/stk",
    )

    request_row = MpesaSTKRequest(
        purpose=MpesaPurpose.RENT,
        phone_number=MpesaService.normalize_phone(payload.phone_number),
        amount=payload.amount,
        invoice_id=invoice.id,
        initiated_by=current_tenant.id,
        checkout_request_id=stk_response.get("CheckoutRequestID"),
        merchant_request_id=stk_response.get("MerchantRequestID"),
    )
    session.add(request_row)
    session.commit()
    session.refresh(request_row)
    return request_row


@router.post("/stk-push/subscription", response_model=MpesaSTKRequestRead)
async def initiate_subscription_stk_push(
    payload: STKPushInitiateSubscription,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    """Landlord pays their RMS subscription."""
    account = session.exec(select(Account).where(Account.landlord_id == current_landlord.id)).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found")

    stk_response = MpesaService.stk_push(
        phone_number=payload.phone_number,
        amount=payload.amount,
        account_reference="RMS-SUB",
        transaction_desc="RMS subscription payment",
        callback_path="/mpesa/callback/stk",
    )

    request_row = MpesaSTKRequest(
        purpose=MpesaPurpose.SUBSCRIPTION,
        phone_number=MpesaService.normalize_phone(payload.phone_number),
        amount=payload.amount,
        account_id=account.id,
        initiated_by=current_landlord.id,
        checkout_request_id=stk_response.get("CheckoutRequestID"),
        merchant_request_id=stk_response.get("MerchantRequestID"),
    )
    session.add(request_row)
    session.commit()
    session.refresh(request_row)
    return request_row


@router.get("/stk-push/{request_id}/status", response_model=MpesaSTKRequestRead)
async def get_stk_push_status(
    request_id,
    current_user: Annotated[User, Depends(require_tenant)],
    session: SessionDep,
):
    """Poll this from the frontend after initiating a push, since the
    callback arrives async and there's no websocket wired up for it here."""
    request_row = session.get(MpesaSTKRequest, request_id)
    if not request_row or request_row.initiated_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return request_row


@router.post("/callback/stk", include_in_schema=False)
async def mpesa_stk_callback(request: Request, session: SessionDep):
    """
    Safaricom hits this — no auth header, no cookies, nothing we control on
    their end. Never raise a non-200 back to Safaricom or they'll retry
    indefinitely; log and swallow instead.
    """
    try:
        body = await request.json()
    except Exception:
        logger.warning("M-Pesa callback: could not parse JSON body")
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    parsed = MpesaService.parse_stk_callback(body)
    checkout_id = parsed.get("checkout_request_id")
    if not checkout_id:
        logger.warning("M-Pesa callback missing CheckoutRequestID: %s", body)
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    request_row = session.exec(
        select(MpesaSTKRequest).where(MpesaSTKRequest.checkout_request_id == checkout_id)
    ).first()
    if not request_row:
        logger.warning("M-Pesa callback for unknown CheckoutRequestID: %s", checkout_id)
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    if request_row.status != MpesaRequestStatus.PENDING:
        # Already processed (Safaricom can resend callbacks) — ack and stop.
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    request_row.updated_at = datetime.now()

    if parsed.get("result_code") != 0:
        request_row.status = MpesaRequestStatus.FAILED
        request_row.result_desc = parsed.get("result_desc")
        session.add(request_row)
        session.commit()
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    request_row.status = MpesaRequestStatus.SUCCESS
    request_row.mpesa_receipt = parsed.get("mpesa_receipt")
    request_row.result_desc = parsed.get("result_desc")
    session.add(request_row)

    try:
        if request_row.purpose == MpesaPurpose.RENT and request_row.invoice_id:
            invoice = session.get(Invoice, request_row.invoice_id)
            tu = session.get(TenantUnit, invoice.tenant_unit_id) if invoice else None
            new_payment = PaymentBase(
                invoice_id=request_row.invoice_id,
                tenant_id=tu.tenant_id if tu else None,
                amount_paid=parsed.get("amount") or request_row.amount,
                transaction_ref=request_row.mpesa_receipt or checkout_id,
                status=ModelPaymentStatus.VERIFIED,
                date_paid=datetime.now(),
            )
            PaymentService.process_new_payment(session, new_payment, request_row.initiated_by)

        elif request_row.purpose == MpesaPurpose.SUBSCRIPTION and request_row.account_id:
            SubscriptionService.activate_subscription_from_payment(
                session,
                account_id=request_row.account_id,
                amount=parsed.get("amount") or request_row.amount,
                reference=request_row.mpesa_receipt or checkout_id,
            )
    except Exception:
        logger.exception("M-Pesa callback processing failed for checkout_id=%s", checkout_id)

    session.commit()
    return {"ResultCode": 0, "ResultDesc": "Accepted"}
