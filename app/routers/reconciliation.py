# app/routers/reconciliation.py
from fastapi import APIRouter, Depends
from typing import Annotated

from app.core.database import SessionDep
from app.core.roles import require_management
from app.models.user import User
from app.services import reconciliation_service

router = APIRouter(
    prefix="/reconciliation",
    tags=["Reconciliation"],
    dependencies=[Depends(require_management)]  # Restricts all routes in this file to Landlords, Caretakers & Property Managers
)

@router.post("/run")
async def reconciliation(
    session: SessionDep,
    current_user: Annotated[User, Depends(require_management)]
):
    """
    Reconciles an uploaded bank/M-Pesa statement in two passes:

    1. Matches any Payment a tenant already claimed (has a transaction_ref)
       against the statement rows, by exact M-Pesa reference.
    2. For statement rows nobody has claimed, auto-matches them by the
       house/account number on the row (the M-Pesa "Account Number" field)
       to whichever tenant currently occupies that house, and creates an
       already-VERIFIED Payment allocated to their oldest outstanding
       invoice - no M-Pesa message needs to ever reach the landlord.

    Anything that still can't be matched after both passes (no reference
    match, and either no house number on the row or that house number
    doesn't resolve to exactly one active tenant) is left PENDING for
    manual review.
    """
    return reconciliation_service.run_full_reconciliation(session, current_user.id)
