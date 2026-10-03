"""add layouts

Revision ID: 5b2e8f4a1c9d
Revises: 3a9c7e5f2d1b
Create Date: 2026-10-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5b2e8f4a1c9d'
down_revision = '3a9c7e5f2d1b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('layouts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    layouts_table = sa.table('layouts',
        sa.column('name', sa.String),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(layouts_table, [
        {'name': 'nalf', 'is_active': True},
    ])


def downgrade():
    op.drop_table('layouts')
