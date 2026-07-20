
# app/services/payment_service.py
from uuid import UUID
from fastapi import HTTPException, status
from sqlmodel import select
from app.models.payment import Payment
from app.models.invoice import Invoice
from app.models.tenant_unit import TenantUnit
from app.schemas.payment import PaymentBase

class PaymentService:
    
    @staticmethod
    def process_new_payment(session, new_payment: PaymentBase, creator_id: UUID) -> Payment:
        payment_dict = new_payment.model_dump()
        payment_dict["created_by"] = creator_id
        
        invoice = None
        if payment_dict.get("invoice_id"):
            invoice = session.get(Invoice, payment_dict["invoice_id"])
            if not invoice:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
            
            if not payment_dict.get("tenant_id"):
                tu = session.get(TenantUnit, invoice.tenant_unit_id)
                if tu:
                    payment_dict["tenant_id"] = tu.tenant_id

        # Calculate rent vs. utilities split based on current unpaid balances
        rent_allocated = 0.0
        utilities_allocated = 0.0
        
        if invoice:
            # Aggregate what has already been paid for this specific invoice
            total_rent_paid_so_far = sum(p.rent_allocated for p in invoice.payments)
            total_util_paid_so_far = sum(p.utilities_allocated for p in invoice.payments)
            
            remaining_rent = max(0.0, (invoice.rent_amount or 0.0) - total_rent_paid_so_far)
            remaining_utils = max(0.0, (invoice.amount or 0.0) - total_util_paid_so_far)
            
            amount_to_distribute = payment_dict["amount_paid"]
            
            # 1. Fill outstanding Rent balance first
            if amount_to_distribute > 0 and remaining_rent > 0:
                allocated_to_rent = min(amount_to_distribute, remaining_rent)
                rent_allocated += allocated_to_rent
                amount_to_distribute -= allocated_to_rent
                
            # 2. Fill outstanding Utilities balance with remaining funds
            if amount_to_distribute > 0 and remaining_utils > 0:
                allocated_to_utils = min(amount_to_distribute, remaining_utils)
                utilities_allocated += allocated_to_utils
                amount_to_distribute -= allocated_to_utils

        payment_dict["rent_allocated"] = rent_allocated
        payment_dict["utilities_allocated"] = utilities_allocated
        
        db_payment = Payment(**payment_dict)
        session.add(db_payment)
        session.commit()
        session.refresh(db_payment)
        
        # Optionally auto-progress invoice status
        if invoice:
            session.refresh(invoice)
            total_paid_now = sum(p.amount_paid for p in invoice.payments)
            total_due = (invoice.rent_amount or 0) + (invoice.amount or 0)
            
            if total_paid_now >= total_due:
                invoice.status = "PAID"
            elif total_paid_now > 0:
                invoice.status = "PARTIALLY_PAID"
                
            session.add(invoice)
            session.commit()
            
        return db_payment