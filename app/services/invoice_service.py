# app/services/invoice_service.py
import pandas as pd
from uuid import UUID
from datetime import datetime
from sqlmodel import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import List

from app.models.invoice import Invoice
from app.models.tenant import Tenant
from app.models.house import House
from app.models.tenant_unit import TenantUnit
from app.models.property import Property
from app.models.utility import UtilityBill
from app.schemas.invoice import InvoiceGenerationRequest, InvoiceStatus
from app.schemas.utility import BillType
from app.schemas.tenant import TenantStatus

class InvoiceService:
    
    @staticmethod
    def get_due_dates(year: int, month: int):
        """
        Generates standard invoicing dates:
        - Generation: 1st of the month
        - Payment target: 5th of the month
        - Deadline: 7th of the month
        """
        gen_date = datetime(year, month, 1)
        due_date = datetime(year, month, 5)
        deadline_date = datetime(year, month, 7)
        return gen_date, due_date, deadline_date

    @classmethod
    async def create_tenant_invoice(
        cls, 
        session, 
        house_id: UUID, 
        utility_list: InvoiceGenerationRequest
    ) -> Invoice:
        house = session.get(House, house_id)
        if not house:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="House not found!")

        tenant_unit = session.exec(
            select(TenantUnit)
            .where(TenantUnit.hse_id == house.id)
            .where(TenantUnit.rent_end == None)
        ).first()

        if not tenant_unit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active tenant found for this unit")

        tenant = session.get(Tenant, tenant_unit.tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        # Static month timing (Current Month, 1st gen, 5th due, 7th deadline)
        now = datetime.now()
        gen_date, due_date, deadline_date = cls.get_due_dates(now.year, now.month)

        base_rent = house.rent
        utilities_total = sum(u.amount for u in utility_list.utilities)
        wallet_deduction = min(tenant.wallet_balance, base_rent + utilities_total)

        invoice = Invoice(
            tenant_unit_id=tenant_unit.id,
            rent_amount=base_rent,
            amount=(base_rent + utilities_total) - wallet_deduction,
            date_of_gen=gen_date,
            date_due=due_date,  # Target 5th
            # Note: Store deadline_date if your schema supports it, or use date_due as the target
        )

        session.add(invoice)
        session.flush()  # Populates invoice.id

        for util in utility_list.utilities:
            saving_util = UtilityBill(
                bill_type=util.bill_type,
                amount=util.amount,
                invoice_id=invoice.id
            )
            session.add(saving_util)

        session.commit()
        session.refresh(invoice)
        return invoice

    @classmethod
    async def update_invoice(
        cls, 
        session, 
        invoice_id: UUID, 
        utility_list: InvoiceGenerationRequest
    ) -> Invoice:
        query = (
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .options(
                selectinload(Invoice.utilities),
                selectinload(Invoice.tenant_unit).selectinload(TenantUnit.house)
            )
        )
        invoice = session.exec(query).first()
        if not invoice:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

        utilities_updates = {u.bill_type: u.amount for u in utility_list.utilities}
        current_utilities_total = 0.0

        for db_util in invoice.utilities:
            if db_util.bill_type in utilities_updates:
                db_util.amount = utilities_updates[db_util.bill_type]
                session.add(db_util)
            current_utilities_total += db_util.amount

        invoice.amount = invoice.rent_amount + current_utilities_total
        session.add(invoice)
        session.commit()
        session.refresh(invoice)
        return invoice

    @classmethod
    async def bulk_upload_invoices(
        cls, 
        session, 
        property_id: UUID, 
        df_dict: dict
    ) -> int:
        new_invoices = []
        
        units = session.exec(select(House).where(House.property_id == property_id)).all()
        units_dict = {str(unit.number): unit for unit in units}

        tenants = session.exec(
            select(Tenant).join(TenantUnit).join(House, House.property_id == property_id)
        ).all()
        tenants_dict = {str(tenant.name): tenant for tenant in tenants}

        tenant_units = session.exec(
            select(TenantUnit).join(House, House.property_id == property_id)
        ).all()
        tenant_units_dict = {(tu.hse_id, tu.tenant_id): tu for tu in tenant_units}

        for sheet_month_name, month_df in df_dict.items():
            required_cols = ["hse_number", "tenant_name", "contact_info", "water_bill", "electricity_bill", "other_utility_bill"]
            if not all(col in month_df.columns for col in required_cols):
                missing_cols = [col for col in required_cols if col not in month_df.columns]
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required columns: {missing_cols}"
                )

            month_df["water_bill"] = pd.to_numeric(month_df["water_bill"], errors="coerce").fillna(0)
            month_df["electricity_bill"] = pd.to_numeric(month_df["electricity_bill"], errors="coerce").fillna(0)
            month_df["other_utility_bill"] = pd.to_numeric(month_df["other_utility_bill"], errors="coerce").fillna(0)

            for index, row in month_df.iterrows():
                hse = units_dict.get(str(row["hse_number"]))
                if not hse:
                    raise Exception(f"House number '{row['hse_number']}' not found in database.")

                tenant = tenants_dict.get(str(row["tenant_name"]))
                tu = tenant_units_dict.get((hse.id, tenant.id)) if tenant else None

                try:
                    month_number = datetime.strptime(sheet_month_name.strip().lower()[:3], "%b").month
                except ValueError:
                    month_number = datetime.now().month  # Fallback

                gen_date, due_date, _ = cls.get_due_dates(2026, month_number)
                utilities_total = float(row["water_bill"]) + float(row["electricity_bill"]) + float(row["other_utility_bill"])

                if not tu:
                    if not tenant:
                        tenant = Tenant(
                            name=str(row["tenant_name"]),
                            email=None,
                            tel=str(row["contact_info"]),
                            status=TenantStatus.VACATED
                        )
                        session.add(tenant)
                        session.flush()
                        tenants_dict[tenant.name] = tenant

                    tu = TenantUnit(
                        tenant_id=tenant.id,
                        hse_id=hse.id,
                        rent_begin=datetime(2026, month_number, 1),
                    )
                    session.add(tu)
                    session.flush()
                    tenant_units_dict[(hse.id, tenant.id)] = tu

                invoice = Invoice(
                    tenant_unit_id=tu.id,
                    rent_amount=hse.rent,
                    amount=hse.rent + utilities_total,
                    date_of_gen=gen_date,
                    date_due=due_date,
                    status=InvoiceStatus.PAID
                )
                session.add(invoice)
                session.flush()

                for bill_type, col_name in [(BillType.WATER, "water_bill"), (BillType.ELECTRICITY, "electricity_bill"), (BillType.OTHER, "other_utility_bill")]:
                    ub = UtilityBill(
                        bill_type=bill_type,
                        amount=float(row[col_name]),
                        invoice_id=invoice.id
                    )
                    session.add(ub)

                new_invoices.append(invoice)

        session.commit()
        return len(new_invoices)