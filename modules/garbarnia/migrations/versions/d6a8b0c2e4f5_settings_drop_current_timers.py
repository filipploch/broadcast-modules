"""settings: usuniecie current_timers (E1)

Revision ID: d6a8b0c2e4f5
Revises: b4f6c8d0e2a3
Create Date: 2026-10-07 00:20:00.000000

Zegary nie sa juz przechowywane w Settings: panel i timer-recovery.js dostaja dane wyliczone z okresu i GameTimer
(core.managers.timer_manager.current_timers_for_game). Downgrade przywraca pusta kolumne.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6a8b0c2e4f5'
down_revision = 'b4f6c8d0e2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE settings_new (
            id INTEGER NOT NULL,
            browse_season_id INTEGER,
            is_scoreboard_reversed BOOLEAN,
            obs_record_filepath VARCHAR(500),
            created_at DATETIME,
            updated_at DATETIME,
            PRIMARY KEY (id),
            FOREIGN KEY (browse_season_id) REFERENCES seasons (id)
        )""")
    op.execute("""
        INSERT INTO settings_new (id, browse_season_id, is_scoreboard_reversed, obs_record_filepath, created_at, updated_at)
        SELECT id, browse_season_id, is_scoreboard_reversed, obs_record_filepath, created_at, updated_at FROM settings""")
    op.execute("DROP TABLE settings")
    op.execute("ALTER TABLE settings_new RENAME TO settings")


def downgrade():
    op.execute("""
        CREATE TABLE settings_old (
            id INTEGER NOT NULL,
            browse_season_id INTEGER,
            current_timers TEXT,
            is_scoreboard_reversed BOOLEAN,
            obs_record_filepath VARCHAR(500),
            created_at DATETIME,
            updated_at DATETIME,
            PRIMARY KEY (id),
            FOREIGN KEY (browse_season_id) REFERENCES seasons (id)
        )""")
    op.execute("""
        INSERT INTO settings_old (id, browse_season_id, is_scoreboard_reversed, obs_record_filepath, created_at, updated_at)
        SELECT id, browse_season_id, is_scoreboard_reversed, obs_record_filepath, created_at, updated_at FROM settings""")
    op.execute("DROP TABLE settings")
    op.execute("ALTER TABLE settings_old RENAME TO settings")
