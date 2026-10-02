"""add is_active to game_events

Revision ID: 3a9c7e5f2d1b
Revises: 7e2b9f4a1c3d
Create Date: 2026-10-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a9c7e5f2d1b'
down_revision = '7e2b9f4a1c3d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.drop_column('is_active')
