"""
Two matching passes over uploaded bank/M-Pesa statement rows:

1. match_by_reference() - a Payment the tenant (or a landlord/caretaker on
   their behalf) already claimed with a transaction_ref gets verified once
   that exact M-Pesa reference/code shows up in an uploaded statement.

2. auto_match_by_house_number() - new. For statement rows nobody has
   claimed at all, match the row's house/account number (the M-Pesa
   "Account Number" field on a paybill statement - landlords here
   near-universally have tenants use their house/unit number for that)
   against the House currently occupied by a TenantUnit. If exactly one
   active tenant occupies that house, a Payment is created automatically -
   status VERIFIED immediately, since the statement itself is the source of
   truth - and allocated against that tenant unit's oldest outstanding
   invoice.

This is what removes the need for tenants to forward their M-Pesa
confirmation messages: once the landlord/caretaker uploads the statement,
both an exact reference match and a house-number match are enough to
reconcile automatically. Anything that matches neither (unrecognized
reference AND no house number on the row, or a house number that doesn't
resolve to exactly one active tenant) is left PENDING for manual review -
auto-matching never guesses when a row is ambiguous.
"""
from typing import Optional
from sqlmodel import Session, select

from app.models.transaction import Transaction
from app.models.payment import Payment
from app.models.house import House
from app.models.tenant_unit import TenantUnit
from app.models.invoice import Invoice
from app.schemas.payment import PaymentStatus
from app.schemas.transaction import TransactionStatus


def match_by_reference(session: Session) -> int:
    payments = session.exec(select(Payment).where(Payment.status == PaymentStatus.UNVERIFIED)).all()
    txns = session.exec(select(Transaction).where(Transaction.transaction_status == TransactionStatus.PENDING)).all()

    txn_map = {t.transaction_reference.strip().upper(): t for t in txns}
    matched_count = 0

    for payment in payments:
        if not payment.transaction_ref:
            continue
        ref_key = payment.transaction_ref.strip().upper()
        if ref_key in txn_map:
            matched_txn = txn_map[ref_key]
            payment.transaction_id = matched_txn.id
            payment.status = PaymentStatus.VERIFIED
            matched_txn.transaction_status = TransactionStatus.MATCHED
            matched_txn.matched_payment_id = payment.id
            session.add(payment)
            session.add(matched_txn)
            matched_count += 1

    return matched_count


def _find_active_tenant_unit_by_house_number(session: Session, house_number: Optional[str]) -> Optional[TenantUnit]:
    """Resolves a house/account number to exactly one currently-occupied
    TenantUnit. If the number matches houses in more than one property (two
    landlords both have a "B2", say) and more than one has an active
    tenant, we deliberately refuse to guess and leave it for manual review."""
    if not house_number or not house_number.strip():
        return None

    houses = session.exec(select(House).where(House.number == house_number.strip())).all()
    if not houses:
        return None

    matches = []
    for house in houses:
        active_unit = session.exec(
            select(TenantUnit)
            .where(TenantUnit.hse_id == house.id)
            .where(TenantUnit.rent_end == None)  # noqa: E711 - still active
        ).first()
        if active_unit:
            matches.append(active_unit)

    if len(matches) == 1:
        return matches[0]
    return None  # zero or ambiguous (>1) matches - leave for a human


def _oldest_unpaid_invoice_for_unit(session: Session, tenant_unit_id) -> Optional[Invoice]:
    return session.exec(
        select(Invoice)
        .where(Invoice.tenant_unit_id == tenant_unit_id)
        .where(Invoice.status != "PAID")
        .order_by(Invoice.date_due.asc())
    ).first()


def auto_match_by_house_number(session: Session, created_by) -> dict:
    from app.services.payment_service import PaymentService
    from app.schemas.payment import PaymentBase

    txns = session.exec(select(Transaction).where(Transaction.transaction_status == TransactionStatus.PENDING)).all()

    auto_matched = 0
    skipped_unresolved = 0

    for txn in txns:
        tenant_unit = _find_active_tenant_unit_by_house_number(session, txn.house_number)
        if not tenant_unit:
            skipped_unresolved += 1
            continue

        invoice = _oldest_unpaid_invoice_for_unit(session, tenant_unit.id)

        new_payment_data = PaymentBase(
            invoice_id=invoice.id if invoice else None,
            tenant_id=tenant_unit.tenant_id,
            amount_paid=txn.amount,
            transaction_ref=txn.transaction_reference,
            status=PaymentStatus.VERIFIED,
            date_paid=txn.transaction_date,
        )
        payment = PaymentService.process_new_payment(session, new_payment_data, created_by)

        txn.transaction_status = TransactionStatus.MATCHED
        txn.matched_payment_id = payment.id
        session.add(txn)
        auto_matched += 1

    return {"auto_matched": auto_matched, "skipped_unresolved": skipped_unresolved}


def run_full_reconciliation(session: Session, created_by) -> dict:
    ref_matches = match_by_reference(session)
    session.commit()

    house_result = auto_match_by_house_number(session, created_by)
    session.commit()

    remaining_pending = session.exec(
        select(Transaction).where(Transaction.transaction_status == TransactionStatus.PENDING)
    ).all()

    return {
        "status": "success",
        "matched_by_reference": ref_matches,
        "auto_matched_by_house_number": house_result["auto_matched"],
        "left_pending_for_manual_review": len(remaining_pending),
    }
