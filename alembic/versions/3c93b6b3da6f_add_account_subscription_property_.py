"""add account, subscription, property_assignment, expense, mpesa_stk_request
and extend transaction for auto-reconciliation; fix paymentstatus enum typo

Revision ID: 3c93b6b3da6f
Revises: 71c4890dee2b
Create Date: 2026-07-15 00:00:00.000000

NOTE on the paymentstatus fix: the initial migration created the Postgres
enum type `paymentstatus` with the literal value 'VERIFIIED' (extra I) —
a typo that never got corrected at the DB level even though the Python
PaymentStatus enum in app/models/payment.py has always said "VERIFIED".
Any code path that tries to write status=PaymentStatus.VERIFIED (including
app/routers/reconciliation.py's existing matching logic, which has a
defensive getattr() working around exactly this) would currently fail
against a real Postgres DB with "invalid input value for enum
paymentstatus". This migration renames the enum label so the value the
application actually writes matches what the column accepts.
"""
from typing import Sequence, Union
from sqlalchemy.dialects import postgresql
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '3c93b6b3da6f'
down_revision: Union[str, Sequence[str], None] = '71c4890dee2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 0. Fix the paymentstatus enum typo (see module docstring) --------
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'paymentstatus' AND e.enumlabel = 'VERIFIIED'
            ) THEN
                ALTER TYPE paymentstatus RENAME VALUE 'VERIFIIED' TO 'VERIFIED';
            END IF;
        END$$;
    """)

    # --- 1. account ---------------------------------------------------
    op.create_table(
        'account',
        sa.Column('business_name', sa.String(), nullable=True),
        sa.Column('account_type', sa.Enum('INDIVIDUAL', 'PROPERTY_MANAGEMENT_COMPANY', name='accounttype'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('landlord_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['landlord_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_account_landlord_id'), 'account', ['landlord_id'], unique=True)
    op.create_index(op.f('ix_account_account_type'), 'account', ['account_type'], unique=False)
    op.create_index(op.f('ix_account_status'), 'account', ['status'], unique=False)

    # --- 2. subscription -----------------------------------------------
    op.create_table(
        'subscription',
        sa.Column('plan', sa.Enum('BASIC', 'STANDARD', 'PROPERTY_MANAGEMENT', name='subscriptionplan'), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('account_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.Enum('TRIALING', 'ACTIVE', 'GRACE', 'SUSPENDED', 'CANCELLED', name='subscriptionstatus'), nullable=False),
        sa.Column('billing_day', sa.Integer(), nullable=False),
        sa.Column('current_period_start', sa.DateTime(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(), nullable=False),
        sa.Column('grace_period_ends_at', sa.DateTime(), nullable=True),
        sa.Column('suspended_at', sa.DateTime(), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('last_payment_ref', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['account.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subscription_account_id'), 'subscription', ['account_id'], unique=False)
    op.create_index(op.f('ix_subscription_plan'), 'subscription', ['plan'], unique=False)
    op.create_index(op.f('ix_subscription_status'), 'subscription', ['status'], unique=False)
    op.create_index(op.f('ix_subscription_is_current'), 'subscription', ['is_current'], unique=False)

    # --- 3. property_assignment ------------------------------------------
    op.create_table(
        'property_assignment',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('property_id', sa.Uuid(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('assigned_by_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['property_id'], ['property.id']),
        sa.ForeignKeyConstraint(['assigned_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_property_assignment_user_id'), 'property_assignment', ['user_id'], unique=False)
    op.create_index(op.f('ix_property_assignment_property_id'), 'property_assignment', ['property_id'], unique=False)

    # --- 4. expense ------------------------------------------------------
    op.create_table(
        'expense',
        sa.Column('property_id', sa.Uuid(), nullable=False),
        sa.Column('house_id', sa.Uuid(), nullable=True),
        sa.Column('category', sa.Enum('MAINTENANCE', 'UTILITIES', 'SECURITY', 'CLEANING', 'STAFF_SALARY', 'LEGAL', 'INSURANCE', 'OTHER', name='expensecategory'), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('status', sa.Enum('PAID', 'OUTSTANDING', name='expensestatus'), nullable=False),
        sa.Column('payment_method', sa.Enum('MPESA', 'BANK', 'CASH', 'OTHER', name='expensepaymentmethod'), nullable=True),
        sa.Column('date_incurred', sa.DateTime(), nullable=False),
        sa.Column('date_paid', sa.DateTime(), nullable=True),
        sa.Column('mpesa_message', sa.String(), nullable=True),
        sa.Column('mpesa_code', sa.String(), nullable=True),
        sa.Column('receipt_photo_path', sa.String(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('landlord_id', sa.Uuid(), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['property.id']),
        sa.ForeignKeyConstraint(['house_id'], ['house.id']),
        sa.ForeignKeyConstraint(['landlord_id'], ['user.id']),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_expense_property_id'), 'expense', ['property_id'], unique=False)
    op.create_index(op.f('ix_expense_house_id'), 'expense', ['house_id'], unique=False)
    op.create_index(op.f('ix_expense_category'), 'expense', ['category'], unique=False)
    op.create_index(op.f('ix_expense_status'), 'expense', ['status'], unique=False)
    op.create_index(op.f('ix_expense_mpesa_code'), 'expense', ['mpesa_code'], unique=False)
    op.create_index(op.f('ix_expense_landlord_id'), 'expense', ['landlord_id'], unique=False)

    # --- 5. mpesa_stk_request --------------------------------------------
    op.create_table(
        'mpesa_stk_request',
        sa.Column('purpose', sa.Enum('RENT', 'SUBSCRIPTION', name='mpesapurpose'), nullable=False),
        sa.Column('phone_number', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('invoice_id', sa.Uuid(), nullable=True),
        sa.Column('account_id', sa.Uuid(), nullable=True),
        sa.Column('initiated_by', sa.Uuid(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('checkout_request_id', sa.String(), nullable=True),
        sa.Column('merchant_request_id', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'SUCCESS', 'FAILED', name='mpesarequeststatus'), nullable=False),
        sa.Column('result_desc', sa.String(), nullable=True),
        sa.Column('mpesa_receipt', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoice.id']),
        sa.ForeignKeyConstraint(['account_id'], ['account.id']),
        sa.ForeignKeyConstraint(['initiated_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_mpesa_stk_request_invoice_id'), 'mpesa_stk_request', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_mpesa_stk_request_account_id'), 'mpesa_stk_request', ['account_id'], unique=False)
    op.create_index(op.f('ix_mpesa_stk_request_checkout_request_id'), 'mpesa_stk_request', ['checkout_request_id'], unique=True)
    op.create_index(op.f('ix_mpesa_stk_request_status'), 'mpesa_stk_request', ['status'], unique=False)

    # --- 6. extend transaction for auto-reconciliation --------------------
    transactionsource_enum = postgresql.ENUM('BANK', 'MPESA', 'MANUAL', name='transactionsource', create_type=False)
    transactionsource_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('transaction', sa.Column('source', transactionsource_enum, nullable=False, server_default='BANK'))
    op.add_column('transaction', sa.Column('house_number', sa.String(), nullable=True))
    op.add_column('transaction', sa.Column('phone_number', sa.String(), nullable=True))
    op.add_column('transaction', sa.Column('payer_name', sa.String(), nullable=True))
    op.add_column('transaction', sa.Column('raw_narrative', sa.String(), nullable=True))
    op.add_column('transaction', sa.Column('matched_payment_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_transaction_house_number'), 'transaction', ['house_number'], unique=False)
    op.create_index(op.f('ix_transaction_phone_number'), 'transaction', ['phone_number'], unique=False)
    op.create_index(op.f('ix_transaction_payer_name'), 'transaction', ['payer_name'], unique=False)
    op.create_index(op.f('ix_transaction_matched_payment_id'), 'transaction', ['matched_payment_id'], unique=False)
    op.create_foreign_key('fk_transaction_matched_payment_id_payment', 'transaction', 'payment', ['matched_payment_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_transaction_matched_payment_id_payment', 'transaction', type_='foreignkey')
    op.drop_index(op.f('ix_transaction_matched_payment_id'), table_name='transaction')
    op.drop_index(op.f('ix_transaction_payer_name'), table_name='transaction')
    op.drop_index(op.f('ix_transaction_phone_number'), table_name='transaction')
    op.drop_index(op.f('ix_transaction_house_number'), table_name='transaction')
    op.drop_column('transaction', 'matched_payment_id')
    op.drop_column('transaction', 'raw_narrative')
    op.drop_column('transaction', 'payer_name')
    op.drop_column('transaction', 'phone_number')
    op.drop_column('transaction', 'house_number')
    op.drop_column('transaction', 'source')
    op.execute("DROP TYPE IF EXISTS transactionsource")

    op.drop_index(op.f('ix_mpesa_stk_request_status'), table_name='mpesa_stk_request')
    op.drop_index(op.f('ix_mpesa_stk_request_checkout_request_id'), table_name='mpesa_stk_request')
    op.drop_index(op.f('ix_mpesa_stk_request_account_id'), table_name='mpesa_stk_request')
    op.drop_index(op.f('ix_mpesa_stk_request_invoice_id'), table_name='mpesa_stk_request')
    op.drop_table('mpesa_stk_request')
    op.execute("DROP TYPE IF EXISTS mpesarequeststatus")
    op.execute("DROP TYPE IF EXISTS mpesapurpose")

    op.drop_index(op.f('ix_expense_landlord_id'), table_name='expense')
    op.drop_index(op.f('ix_expense_mpesa_code'), table_name='expense')
    op.drop_index(op.f('ix_expense_status'), table_name='expense')
    op.drop_index(op.f('ix_expense_category'), table_name='expense')
    op.drop_index(op.f('ix_expense_house_id'), table_name='expense')
    op.drop_index(op.f('ix_expense_property_id'), table_name='expense')
    op.drop_table('expense')
    op.execute("DROP TYPE IF EXISTS expensepaymentmethod")
    op.execute("DROP TYPE IF EXISTS expensestatus")
    op.execute("DROP TYPE IF EXISTS expensecategory")

    op.drop_index(op.f('ix_property_assignment_property_id'), table_name='property_assignment')
    op.drop_index(op.f('ix_property_assignment_user_id'), table_name='property_assignment')
    op.drop_table('property_assignment')

    op.drop_index(op.f('ix_subscription_is_current'), table_name='subscription')
    op.drop_index(op.f('ix_subscription_status'), table_name='subscription')
    op.drop_index(op.f('ix_subscription_plan'), table_name='subscription')
    op.drop_index(op.f('ix_subscription_account_id'), table_name='subscription')
    op.drop_table('subscription')
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
    op.execute("DROP TYPE IF EXISTS subscriptionplan")

    op.drop_index(op.f('ix_account_status'), table_name='account')
    op.drop_index(op.f('ix_account_account_type'), table_name='account')
    op.drop_index(op.f('ix_account_landlord_id'), table_name='account')
    op.drop_table('account')
    op.execute("DROP TYPE IF EXISTS accounttype")

    # Intentionally NOT reverting the paymentstatus enum rename — going
    # back to the 'VERIFIIED' typo would just resurrect the bug.
