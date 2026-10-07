"""Migracja bazy modułu do aktualnej wersji (kopia zapasowa, upgrade, sprawdzenie).

    python modules\\migrate_db.py futsal_nalf|garbarnia          (z folderu głównego projektu)

Baza: domyślnie modules/<moduł>/instance/database.db, albo ta ze zmiennej DATABASE_URL (np. baza testowa).
Przed zmianą skrypt kopiuje plik bazy obok siebie jako <nazwa>.bak_RRRRMMDD_GGMMSS (jak dotychczasowe kopie zapasowe).
Jeśli baza jest już aktualna, nic nie zmienia i nie robi kopii. Nie uruchamia menedżerów ani nie łączy się z HUB-em.
"""
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

MODULES = Path(__file__).resolve().parent
module = sys.argv[1] if len(sys.argv) > 1 else None
if module not in ('futsal_nalf', 'garbarnia'):
    sys.exit('Użycie: python modules\\migrate_db.py futsal_nalf|garbarnia')

MODULE_DIR = MODULES / module
sys.path[:0] = [str(MODULE_DIR), str(MODULES)]
os.chdir(MODULE_DIR)

from core.utils.schema_check import schema_status, resolve_db_url  # noqa: E402

db_url = os.environ.get('DATABASE_URL') or 'sqlite:///database.db'
instance = MODULE_DIR / 'instance'
info = schema_status(db_url, str(instance), MODULE_DIR / 'migrations')
print(f'Baza: {info["db_path"]}')
print(f'Wersja w bazie: {", ".join(info["current"]) or "brak"} | wymagana: {", ".join(info["heads"])}')
if info['state'] == 'ok':
    print('Baza jest aktualna. Nic do zrobienia.')
    sys.exit(0)
if info['state'] == 'ahead':
    sys.exit('Baza jest NOWSZA niż kod modułu; migrator jej nie cofa. Użyj nowszej wersji kodu.')
if info['state'] in ('missing', 'empty'):
    sys.exit('Baza nie istnieje albo jest pusta; najpierw utwórz ją (db_init.py w folderze modułu).')
if info['state'] == 'unversioned':
    sys.exit('Baza ma tabele, ale nie ma tabeli alembic_version. Nie zgaduję wersji: napisz do mnie, jak ją oznaczyć (stamp).')

engine_url, path = resolve_db_url(db_url, str(instance))
if path:
    backup = f'{path}.bak_{datetime.now():%Y%m%d_%H%M%S}'
    shutil.copy(path, backup)
    print(f'Kopia zapasowa: {backup}')

os.environ['BM_TEST_DATABASE_URL'] = engine_url      # konfiguracja 'testing': bez menedżerów i bez połączenia z HUB-em
from app import create_app          # noqa: E402
import flask_migrate                # noqa: E402

app = create_app('testing')
with app.app_context():
    flask_migrate.upgrade(directory=str(MODULE_DIR / 'migrations'))
after = schema_status(db_url, str(instance), MODULE_DIR / 'migrations')
print(f'Wersja po migracji: {", ".join(after["current"])}')
if after['state'] != 'ok':
    sys.exit('Migracja nie doprowadziła bazy do aktualnej wersji. Przywróć kopię zapasową i napisz do mnie.')
print('Gotowe: baza jest aktualna.')
