"""
migrate_add_allows_draw.py
──────────────────────────
Migracja: dodanie kolumny allows_draw (BOOLEAN) do tabeli leagues.

Domyślna wartość: True (liga grupowa — remis dozwolony).
Istniejące rekordy otrzymują True — bezpieczne, nie zmienia logiki
dotychczasowych lig grupowych. Ligi pucharowe należy ręcznie
zaktualizować przez panel edycji ligi.

Uruchomienie:
    python migrate_add_allows_draw.py

Skrypt jest idempotentny — jeśli kolumna już istnieje, kończy się bez błędu.
"""

def run_migration():
    from app import create_app
    from app.extensions import db

    app = create_app('development')

    with app.app_context():
        inspector = db.inspect(db.engine)

        cols = {c['name'] for c in inspector.get_columns('leagues')}
        if 'allows_draw' in cols:
            print("ℹ️  Kolumna 'allows_draw' już istnieje — migracja nie jest potrzebna.")
            return

        print("=" * 60)
        print("  Migracja: leagues.allows_draw")
        print("=" * 60)

        print("\n📋 Dodaję kolumnę 'allows_draw' do tabeli 'leagues'...")

        with db.engine.connect() as conn:
            # SQLite nie obsługuje ADD COLUMN z NOT NULL bez DEFAULT w ALTER TABLE,
            # dlatego używamy DEFAULT 1 (TRUE) bezpośrednio w DDL.
            conn.execute(db.text(
                "ALTER TABLE leagues ADD COLUMN allows_draw BOOLEAN NOT NULL DEFAULT 1"
            ))
            conn.commit()

        print("   ✅ Kolumna dodana")

        # Weryfikacja
        inspector = db.inspect(db.engine)
        cols = {c['name'] for c in inspector.get_columns('leagues')}
        assert 'allows_draw' in cols, "Kolumna nie została dodana!"

        # Pokaż aktualne wartości
        with db.engine.connect() as conn:
            rows = conn.execute(
                db.text("SELECT id, name, allows_draw FROM leagues")
            ).fetchall()

        print("\n📊 Aktualne ligi po migracji:")
        for row in rows:
            flag = "✅ remis dozwolony" if row[2] else "⚽ pucharowe"
            print(f"   ID={row[0]}  {row[1]:30}  {flag}")

        print("\n💡 Pamiętaj: ustaw allows_draw=False dla lig pucharowych")
        print("   w panelu edycji ligi (Ligi → Edytuj).")
        print("\n✅ Migracja zakończona pomyślnie!")
        print("=" * 60)


if __name__ == '__main__':
    run_migration()
