"""
Manual cascade-delete helpers.

None of the FKs in this schema have ON DELETE CASCADE at the DB level, so
deleting a parent row (Property, House, Tenant, User/Landlord) directly would
just throw an IntegrityError. These functions delete children in the correct
leaf-to-root order using the ORM, so SQLAlchemy's session.delete() cascades
(e.g. Invoice -> UtilityBill, which already has cascade_delete=True) still
fire correctly along the way.

All functions operate on an existing session and do NOT commit — the caller
commits once at the end of the whole operation, so a failure partway through
rolls back everything instead of leaving a half-deleted tree.
"""
from sqlmodel import Session, select

from app.models.tenant_unit import TenantUnit
from app.models.tenant import Tenant
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.house import House
from app.models.property import Property
from app.models.maintenance_bill import MaintenanceBill
from app.models.user import User


def delete_tenant_unit_cascade(session: Session, tenant_unit: TenantUnit) -> None:
    """Deletes a single tenancy (unit assignment) and everything billed under it."""
    invoices = session.exec(
        select(Invoice).where(Invoice.tenant_unit_id == tenant_unit.id)
    ).all()

    for invoice in invoices:
        payments = session.exec(
            select(Payment).where(Payment.invoice_id == invoice.id)
        ).all()
        for payment in payments:
            session.delete(payment)

        # invoice.utilities has cascade_delete=True already, so deleting the
        # Invoice via the ORM (not raw SQL) takes its UtilityBills with it.
        session.delete(invoice)

    session.delete(tenant_unit)


def delete_tenant_full_cascade(session: Session, tenant: Tenant) -> None:
    """Deletes a tenant entirely: every unit they've held, their linked login
    account (if any), and the tenant business record itself."""
    units = session.exec(
        select(TenantUnit).where(TenantUnit.tenant_id == tenant.id)
    ).all()

    for unit in units:
        delete_tenant_unit_cascade(session, unit)

    if tenant.user_id:
        linked_user = session.get(User, tenant.user_id)
        if linked_user:
            session.delete(linked_user)

    session.delete(tenant)


def delete_house_cascade(session: Session, house: House) -> None:
    bills = session.exec(
        select(MaintenanceBill).where(MaintenanceBill.hse_id == house.id)
    ).all()
    for bill in bills:
        session.delete(bill)

    units = session.exec(
        select(TenantUnit).where(TenantUnit.hse_id == house.id)
    ).all()
    for unit in units:
        tenant = session.get(Tenant, unit.tenant_id)
        if tenant:
            delete_tenant_full_cascade(session, tenant)
        else:
            delete_tenant_unit_cascade(session, unit)

    session.delete(house)


def delete_property_cascade(session: Session, property: Property) -> None:
    houses = session.exec(
        select(House).where(House.property_id == property.id)
    ).all()
    for house in houses:
        delete_house_cascade(session, house)

    session.delete(property)


def delete_landlord_cascade(session: Session, landlord: User) -> None:
    """Deletes a landlord and everything connected to them: every property
    (and its houses/tenants/invoices/payments), every caretaker they created,
    and finally the landlord's own account."""
    properties = session.exec(
        select(Property).where(Property.landlord_id == landlord.id)
    ).all()
    for property in properties:
        delete_property_cascade(session, property)

    dependents = session.exec(
        select(User).where(User.landlord_id == landlord.id)
    ).all()
    for dependent in dependents:
        session.delete(dependent)

    session.delete(landlord)
