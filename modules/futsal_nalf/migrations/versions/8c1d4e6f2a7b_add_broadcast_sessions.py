"""add broadcast sessions (E1)

Revision ID: 8c1d4e6f2a7b
Revises: 5b2e8f4a1c9d
Create Date: 2026-10-07 00:00:00.000000

Tabele sesji transmisji i meczow w sesji. Ograniczenia: najwyzej jedna sesja otwarta (UNIQUE open_slot),
najwyzej jeden mecz aktywny w sesji (UNIQUE session_id + active_slot).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c1d4e6f2a7b'
down_revision = '5b2e8f4a1c9d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('broadcast_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('open_slot', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('obs_scene', sa.String(length=200), nullable=True),
        sa.Column('obs_recording', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('obs_streaming', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('recovery_state', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('open_slot'),
    )
    op.create_index(op.f('ix_broadcast_sessions_status'), 'broadcast_sessions', ['status'], unique=False)

    op.create_table('session_games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('active_slot', sa.Integer(), nullable=True),
        sa.Column('profile_key', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['games.id']),
        sa.ForeignKeyConstraint(['session_id'], ['broadcast_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'game_id', name='uq_session_game'),
        sa.UniqueConstraint('session_id', 'position', name='uq_session_position'),
        sa.UniqueConstraint('session_id', 'active_slot', name='uq_session_active'),
    )
    op.create_index(op.f('ix_session_games_game_id'), 'session_games', ['game_id'], unique=False)
    op.create_index(op.f('ix_session_games_session_id'), 'session_games', ['session_id'], unique=False)
    op.create_index(op.f('ix_session_games_status'), 'session_games', ['status'], unique=False)


def downgrade():
    op.drop_table('session_games')
    op.drop_table('broadcast_sessions')
