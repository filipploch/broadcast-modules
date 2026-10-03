"""add layouts

Revision ID: 2d7f9a3c6b1e
Revises: 6f2d8a4c1e7b
Create Date: 2026-10-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2d7f9a3c6b1e'
down_revision = '6f2d8a4c1e7b'
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
        {'name': 'garbarnia', 'is_active': True},
    ])


def downgrade():
    op.drop_table('layouts')
