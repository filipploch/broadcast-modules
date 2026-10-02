"""add is_active to game_events

Revision ID: 6f2d8a4c1e7b
Revises: a1f3c8e2b9d6
Create Date: 2026-10-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6f2d8a4c1e7b'
down_revision = 'a1f3c8e2b9d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.drop_column('is_active')
