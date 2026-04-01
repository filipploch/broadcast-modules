"""
migrate_add_game_timers.py
──────────────────────────
Migracja: dodanie tabeli game_timers.

Projekt nie używa Alembic — migracje wykonywane są ręcznie przez
dedykowane skrypty operujące bezpośrednio na SQLAlchemy / silniku SQL.

Uruchomienie:
    python migrate_add_game_timers.py

Skrypt jest idempotentny — jeśli tabela już istnieje, kończy się bez błędu.
Można go bezpiecznie uruchamiać wielokrotnie.
"""

import sys
import textwrap
from datetime import datetime


def run_migration():
    from app import create_app
    from app.extensions import db

    app = create_app('development')

    with app.app_context():
        inspector = db.inspect(db.engine)
        existing_tables = inspector.get_table_names()

        # ── Sprawdzenie czy migracja jest potrzebna ────────────────────────
        if 'game_timers' in existing_tables:
            print("ℹ️  Tabela 'game_timers' już istnieje — migracja nie jest potrzebna.")
            return

        print("=" * 60)
        print("  Migracja: dodanie tabeli game_timers")
        print("=" * 60)

        # ── Utworzenie tabeli przez ORM ────────────────────────────────────
        # Import modelu musi nastąpić wewnątrz app_context, żeby metadane
        # SQLAlchemy były prawidłowo zarejestrowane.
        from app.models.game_timer import GameTimer  # noqa: F401

        print("\n📋 Tworzę tabelę 'game_timers'...")
        GameTimer.__table__.create(db.engine)
        print("   ✅ Tabela utworzona")

        # ── Weryfikacja struktury ──────────────────────────────────────────
        inspector = db.inspect(db.engine)
        columns = {c['name']: c for c in inspector.get_columns('game_timers')}
        indexes = {i['name']: i for i in inspector.get_indexes('game_timers')}

        expected_columns = [
            'id', 'game_id', 'period_id', 'timer_type', 'team', 'player_id',
            'plugin_timer_id', 'elapsed_time_ms', 'limit_ms', 'state',
            'start_offset_ms', 'adjustment_ms', 'created_at', 'updated_at',
        ]
        expected_indexes = [
            'ix_game_timer_game_state',
            'ix_game_timer_game_type_team',
        ]

        print("\n📊 Weryfikacja kolumn:")
        all_ok = True
        for col in expected_columns:
            if col in columns:
                print(f"   ✅ {col}")
            else:
                print(f"   ❌ BRAK: {col}")
                all_ok = False

        print("\n📊 Weryfikacja indeksów:")
        for idx in expected_indexes:
            if idx in indexes:
                print(f"   ✅ {idx}")
            else:
                print(f"   ❌ BRAK: {idx}")
                all_ok = False

        if all_ok:
            print("\n✅ Migracja zakończona pomyślnie!")
        else:
            print("\n⚠️  Migracja zakończona z ostrzeżeniami — sprawdź powyższe błędy.")

        # ── Wypisz DDL dla dokumentacji ────────────────────────────────────
        print("\n📄 Struktura tabeli:")
        for col_name, col in columns.items():
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            default  = f" DEFAULT {col['default']}" if col.get('default') else ""
            print(f"   {col_name:25} {str(col['type']):20} {nullable}{default}")

        print("\n" + "=" * 60)


if __name__ == '__main__':
    run_migration()
