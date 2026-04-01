"""
migrate_shootout_kick_player_nullable.py
─────────────────────────────────────────
Migracja: zmiana player_id w tabeli shootout_kicks na nullable.

Uruchomienie:
    python migrate_shootout_kick_player_nullable.py

Skrypt jest idempotentny.
"""


def run_migration():
    from app import create_app
    from app.extensions import db
    from sqlalchemy import text

    app = create_app('development')

    with app.app_context():
        inspector = db.inspect(db.engine)

        # Sprawdź aktualny stan kolumny
        columns = {c['name']: c for c in inspector.get_columns('shootout_kicks')}

        if 'player_id' not in columns:
            print("❌ Kolumna 'player_id' nie istnieje w tabeli shootout_kicks")
            return

        if columns['player_id']['nullable']:
            print("ℹ️  Kolumna 'player_id' jest już nullable — migracja nie jest potrzebna.")
            return

        print("=" * 60)
        print("  Migracja: player_id nullable w shootout_kicks")
        print("=" * 60)

        # SQLite nie ma ALTER COLUMN — przebudowa tabeli
        print("\n📋 Przebudowuję tabelę shootout_kicks...")

        db.session.execute(text("""
            CREATE TABLE shootout_kicks_new (
                id          INTEGER NOT NULL PRIMARY KEY,
                shootout_id INTEGER NOT NULL,
                game_id     INTEGER NOT NULL,
                player_id   INTEGER,
                team        VARCHAR(10) NOT NULL,
                round_number INTEGER NOT NULL,
                kick_order  INTEGER NOT NULL,
                scored      BOOLEAN,
                created_at  DATETIME NOT NULL,
                updated_at  DATETIME NOT NULL,
                FOREIGN KEY(shootout_id) REFERENCES shootouts(id),
                FOREIGN KEY(game_id)     REFERENCES games(id),
                FOREIGN KEY(player_id)   REFERENCES players(id),
                CONSTRAINT uq_shootout_kick_position
                    UNIQUE (shootout_id, round_number, kick_order)
            )
        """))

        db.session.execute(text("""
            INSERT INTO shootout_kicks_new
            SELECT id, shootout_id, game_id, player_id, team,
                   round_number, kick_order, scored, created_at, updated_at
            FROM shootout_kicks
        """))

        db.session.execute(text("DROP TABLE shootout_kicks"))
        db.session.execute(text("ALTER TABLE shootout_kicks_new RENAME TO shootout_kicks"))
        db.session.commit()

        # Odtwórz indeksy
        db.session.execute(text("""
            CREATE INDEX ix_shootout_kick_shootout_round
            ON shootout_kicks (shootout_id, round_number)
        """))
        db.session.execute(text("""
            CREATE INDEX ix_shootout_kick_game_round
            ON shootout_kicks (game_id, round_number)
        """))
        db.session.execute(text("""
            CREATE INDEX ix_shootout_kicks_player_id
            ON shootout_kicks (player_id)
        """))

        print("   ✅ Tabela przebudowana")

        # Weryfikacja
        inspector = db.inspect(db.engine)
        columns = {c['name']: c for c in inspector.get_columns('shootout_kicks')}
        player_nullable = columns['player_id']['nullable']

        if player_nullable:
            print("\n✅ Migracja zakończona pomyślnie — player_id jest teraz nullable.")
        else:
            print("\n❌ Coś poszło nie tak — player_id nadal NOT NULL.")

        print("\n" + "=" * 60)


if __name__ == '__main__':
    run_migration()