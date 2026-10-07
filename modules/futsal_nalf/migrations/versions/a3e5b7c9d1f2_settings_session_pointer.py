"""settings: wskaznik meczu zastapiony sesja transmisji (E1)

Revision ID: a3e5b7c9d1f2
Revises: 8c1d4e6f2a7b
Create Date: 2026-10-07 00:10:00.000000

- dodaje settings.browse_season_id (sezon wybrany do przegladania list; wartosc poczatkowa = dotychczasowy current_season_id)
- usuwa current_game_id, current_period_id, current_season_id, current_shootout_id (stan wynika teraz z sesji transmisji)
Po migracji nie ma otwartej sesji transmisji (wskaznik 'ostatnio wybrany' nie jest 'na antenie').
Downgrade przywraca kolumny (current_season_id z browse_season_id; pozostale puste).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3e5b7c9d1f2'
down_revision = '8c1d4e6f2a7b'
branch_labels = None
depends_on = None


def upgrade():
    # Tabela przebudowana jawnie (SQLite): w starszych bazach settings ma klucz obcy do nieistniejącej tabeli 'penalties'
    # (pozostałość po zmianie nazwy), którego Alembic w trybie wsadowym nie potrafi odtworzyć.
    op.execute("""
        CREATE TABLE settings_new (
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
        INSERT INTO settings_new (id, browse_season_id, current_timers, is_scoreboard_reversed,
                                  obs_record_filepath, created_at, updated_at)
        SELECT id, current_season_id, current_timers, is_scoreboard_reversed,
               obs_record_filepath, created_at, updated_at FROM settings""")
    op.execute("DROP TABLE settings")
    op.execute("ALTER TABLE settings_new RENAME TO settings")


def downgrade():
    op.execute("""
        CREATE TABLE settings_old (
            id INTEGER NOT NULL,
            current_season_id INTEGER,
            current_game_id INTEGER,
            current_period_id INTEGER,
            current_timers TEXT,
            is_scoreboard_reversed BOOLEAN,
            obs_record_filepath VARCHAR(500),
            created_at DATETIME,
            updated_at DATETIME,
            current_shootout_id INTEGER,
            PRIMARY KEY (id),
            FOREIGN KEY (current_game_id) REFERENCES games (id),
            FOREIGN KEY (current_period_id) REFERENCES periods (id),
            FOREIGN KEY (current_shootout_id) REFERENCES shootouts (id),
            FOREIGN KEY (current_season_id) REFERENCES seasons (id)
        )""")
    op.execute("""
        INSERT INTO settings_old (id, current_season_id, current_timers, is_scoreboard_reversed,
                                  obs_record_filepath, created_at, updated_at)
        SELECT id, browse_season_id, current_timers, is_scoreboard_reversed,
               obs_record_filepath, created_at, updated_at FROM settings""")
    op.execute("DROP TABLE settings")
    op.execute("ALTER TABLE settings_old RENAME TO settings")
