"""
migrate_add_shootout_kicks.py
─────────────────────────────
Migracja: dodanie tabeli shootout_kicks.

Projekt nie używa Alembic — migracje wykonywane są ręcznie przez
dedykowane skrypty operujące bezpośrednio na SQLAlchemy / silniku SQL.

Uruchomienie:
    python migrate_add_shootout_kicks.py

Skrypt jest idempotentny — jeśli tabela już istnieje, kończy się bez błędu.
Można go bezpiecznie uruchamiać wielokrotnie.
"""


def run_migration():
    from app import create_app
    from app.extensions import db

    app = create_app('development')

    with app.app_context():
        inspector = db.inspect(db.engine)
        existing_tables = inspector.get_table_names()

        # ── Sprawdzenie czy migracja jest potrzebna ────────────────────────
        if 'shootout_kicks' in existing_tables:
            print("ℹ️  Tabela 'shootout_kicks' już istnieje — migracja nie jest potrzebna.")
            return

        print("=" * 60)
        print("  Migracja: dodanie tabeli shootout_kicks")
        print("=" * 60)

        from app.models.shootout_kick import ShootoutKick  # noqa: F401

        print("\n📋 Tworzę tabelę 'shootout_kicks'...")
        ShootoutKick.__table__.create(db.engine)
        print("   ✅ Tabela utworzona")

        # ── Weryfikacja struktury ──────────────────────────────────────────
        inspector = db.inspect(db.engine)
        columns = {c['name']: c for c in inspector.get_columns('shootout_kicks')}
        indexes = {i['name']: i for i in inspector.get_indexes('shootout_kicks')}

        expected_columns = [
            'id', 'shootout_id', 'game_id', 'player_id',
            'team', 'round_number', 'kick_order', 'scored',
            'created_at', 'updated_at',
        ]
        expected_indexes = [
            'ix_shootout_kick_shootout_round',
            'ix_shootout_kick_game_round',
            'uq_shootout_kick_position',
        ]

        print("\n📊 Weryfikacja kolumn:")
        all_ok = True
        for col in expected_columns:
            if col in columns:
                print(f"   ✅ {col}")
            else:
                print(f"   ❌ BRAK: {col}")
                all_ok = False

        print("\n📊 Weryfikacja indeksów i ograniczeń:")
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
