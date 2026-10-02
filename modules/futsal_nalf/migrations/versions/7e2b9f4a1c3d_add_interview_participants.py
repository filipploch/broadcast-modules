"""add interview_participants

Revision ID: 7e2b9f4a1c3d
Revises: 9d1e5c3b7a2f
Create Date: 2026-10-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e2b9f4a1c3d'
down_revision = '9d1e5c3b7a2f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('interview_participants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('interview_type', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('matched_player_id', sa.Integer(), nullable=True),
    sa.Column('matched_referee_id', sa.Integer(), nullable=True),
    sa.Column('matched_commentator_id', sa.Integer(), nullable=True),
    sa.Column('matched_team_id', sa.Integer(), nullable=True),
    sa.Column('use_team_crest', sa.Boolean(), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('image_path', sa.String(length=500), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
    sa.ForeignKeyConstraint(['matched_player_id'], ['players.id'], ),
    sa.ForeignKeyConstraint(['matched_referee_id'], ['referees.id'], ),
    sa.ForeignKeyConstraint(['matched_commentator_id'], ['commentators.id'], ),
    sa.ForeignKeyConstraint(['matched_team_id'], ['teams.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('interview_participants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_interview_participants_game_id'), ['game_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_interview_participants_is_active'), ['is_active'], unique=False)


def downgrade():
    with op.batch_alter_table('interview_participants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_interview_participants_is_active'))
        batch_op.drop_index(batch_op.f('ix_interview_participants_game_id'))

    op.drop_table('interview_participants')
