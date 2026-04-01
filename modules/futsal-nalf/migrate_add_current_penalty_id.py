"""
migrate_add_current_penalty_id.py
──────────────────────────────────
Migracja: dodanie kolumny current_penalty_id (INTEGER, FK → penalties.id)
do tabeli settings.

Uruchomienie:
    python migrate_add_current_penalty_id.py

Skrypt jest idempotentny.
"""


def run_migration():
    from app import create_app
    from app.extensions import db

    app = create_app('development')

    with app.app_context():
        inspector = db.inspect(db.engine)
        cols = {c['name'] for c in inspector.get_columns('settings')}

        if 'current_penalty_id' in cols:
            print("ℹ️  Kolumna 'current_penalty_id' już istnieje — migracja nie jest potrzebna.")
            return

        print("=" * 60)
        print("  Migracja: settings.current_penalty_id")
        print("=" * 60)

        print("\n📋 Dodaję kolumnę 'current_penalty_id' do tabeli 'settings'...")

        with db.engine.connect() as conn:
            conn.execute(db.text(
                "ALTER TABLE settings ADD COLUMN current_penalty_id INTEGER "
                "REFERENCES penalties(id)"
            ))
            conn.commit()

        inspector = db.inspect(db.engine)
        cols = {c['name'] for c in inspector.get_columns('settings')}
        assert 'current_penalty_id' in cols

        print("   ✅ Kolumna dodana")
        print("\n✅ Migracja zakończona pomyślnie!")
        print("=" * 60)


if __name__ == '__main__':
    run_migration()
