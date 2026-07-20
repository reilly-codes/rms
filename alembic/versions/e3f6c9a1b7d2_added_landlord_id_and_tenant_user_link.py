"""added landlord_id to user and user_id to tenant for auth hierarchy

Revision ID: e3f6c9a1b7d2
Revises: a5997a46cd22
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e3f6c9a1b7d2'
down_revision: Union[str, Sequence[str], None] = 'a5997a46cd22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user', sa.Column('landlord_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_user_landlord_id'), 'user', ['landlord_id'], unique=False)
    op.create_foreign_key('fk_user_landlord_id_user', 'user', 'user', ['landlord_id'], ['id'])

    op.add_column('tenant', sa.Column('user_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_tenant_user_id'), 'tenant', ['user_id'], unique=True)
    op.create_foreign_key('fk_tenant_user_id_user', 'tenant', 'user', ['user_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_tenant_user_id_user', 'tenant', type_='foreignkey')
    op.drop_index(op.f('ix_tenant_user_id'), table_name='tenant')
    op.drop_column('tenant', 'user_id')

    op.drop_constraint('fk_user_landlord_id_user', 'user', type_='foreignkey')
    op.drop_index(op.f('ix_user_landlord_id'), table_name='user')
    op.drop_column('user', 'landlord_id')
    