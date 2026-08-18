"""add helper relay tables (helpers, helper_event_candidates, helper_event_submissions)

Revision ID: 3b7e9f2a1c4d
Revises: 4d8e2a1f6c9b
Create Date: 2026-07-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3b7e9f2a1c4d'
down_revision = '4d8e2a1f6c9b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'helpers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('external_id', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('external_id'),
    )
    op.create_index('ix_helpers_external_id', 'helpers', ['external_id'])

    op.create_table(
        'helper_event_candidates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_id', sa.Integer(), sa.ForeignKey('games.id'), nullable=False),
        sa.Column('period_id', sa.Integer(), sa.ForeignKey('periods.id'), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='new'),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('events.id'), nullable=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=True),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id'), nullable=True),
        sa.Column('event_time_delta_s', sa.Integer(), nullable=False),
        sa.Column('comment', sa.String(length=500), nullable=True),
        sa.Column('source_game_event_id', sa.Integer(), sa.ForeignKey('game_events.id'), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('status_reason', sa.String(length=300), nullable=True),
        sa.Column('resolved_game_event_id', sa.Integer(), sa.ForeignKey('game_events.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_hec_game_id', 'helper_event_candidates', ['game_id'])
    op.create_index('ix_hec_period_id', 'helper_event_candidates', ['period_id'])
    op.create_index('ix_hec_source_game_event_id', 'helper_event_candidates', ['source_game_event_id'])
    op.create_index('ix_hec_status', 'helper_event_candidates', ['status'])

    op.create_table(
        'helper_event_submissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('helper_id', sa.Integer(), sa.ForeignKey('helpers.id'), nullable=False),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('helper_event_candidates.id'), nullable=False),
        sa.Column('game_id', sa.Integer(), sa.ForeignKey('games.id'), nullable=False),
        sa.Column('period_id', sa.Integer(), sa.ForeignKey('periods.id'), nullable=False),
        sa.Column('event_time_delta_s', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('events.id'), nullable=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=True),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id'), nullable=True),
        sa.Column('comment', sa.String(length=500), nullable=True),
        sa.Column('source_game_event_id', sa.Integer(), sa.ForeignKey('game_events.id'), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_hes_helper_id', 'helper_event_submissions', ['helper_id'])
    op.create_index('ix_hes_candidate_id', 'helper_event_submissions', ['candidate_id'])
    op.create_index('ix_hes_game_id', 'helper_event_submissions', ['game_id'])
    op.create_index('ix_hes_period_id', 'helper_event_submissions', ['period_id'])


def downgrade():
    op.drop_table('helper_event_submissions')
    op.drop_table('helper_event_candidates')
    op.drop_index('ix_helpers_external_id', table_name='helpers')
    op.drop_table('helpers')
