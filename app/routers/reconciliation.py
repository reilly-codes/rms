from fastapi import APIRouter, Depends
from sqlmodel import select

from app.db import SessionDep
from app.models.transaction import Transaction
from app.models.payment import Payment
from app.schemas.payment import PaymentStatus
from app.schemas.transaction import TransactionStatus
from app.routers.users import active_user

router = APIRouter(
    dependencies=[Depends(active_user)]
)

@router.post("/reconciliation/run")  
async def reconciliation(
    session: SessionDep
):
    payments_query = select(Payment).where(Payment.status == PaymentStatus.UNVERIFIED)
    payments = session.exec(payments_query).all()
    
    txn_query = select(Transaction).where(Transaction.transaction_status == TransactionStatus.PENDING)
    txn = session.exec(txn_query).all()
    
    txn_map = {t.transaction_reference.strip().upper(): t for t in txn}
    matched_count = 0
    
    for payment in payments:
        if payment.transaction_ref.strip().upper() in txn_map:
            matched_txn = txn_map[payment.transaction_ref]
            payment.transaction_id = matched_txn.id
            payment.status = PaymentStatus.VERIFIIED
            matched_txn.transaction_status = TransactionStatus.MATCHED
            
            session.add(payment)
            session.add(matched_txn)
            
            matched_count += 1
            
    session.commit()
    
    return {
        "status": "success", 
        "matches_found": matched_count,
        "remaining_unverified": len(payments) - matched_count
    }