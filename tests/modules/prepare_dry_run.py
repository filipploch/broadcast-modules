"""Przygotowanie bazy testowej do proby na sucho (E1): kopia lokalnej bazy modulu, migracja do najnowszej wersji,
test dymny tras GET na prawdziwych danych.

    python tests/modules/prepare_dry_run.py [futsal_nalf|garbarnia]

Nie dotyka oryginalu (modules/<modul>/instance/database.db) ani folderu transmisyjnego. Wynik: modules/<modul>/instance/database-proba.db
(katalog instance jest poza gitem). Na koncu wypisuje polecenie uruchomienia modulu na tej bazie.
"""
import os, pathlib, shutil, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
module = sys.argv[1] if len(sys.argv) > 1 else "futsal_nalf"
src = REPO / "modules" / module / "instance" / "database.db"
dst = REPO / "modules" / module / "instance" / "database-proba.db"
shutil.copy(src, dst)

os.environ["BM_TEST_DATABASE_URL"] = "sqlite:///" + dst.as_posix()
sys.path[:0] = [str(REPO / "modules" / module), str(REPO / "modules")]
os.chdir(REPO / "modules" / module)
from app import create_app
import flask_migrate

app = create_app("testing")
with app.app_context():
    flask_migrate.upgrade(directory=str(REPO / "modules" / module / "migrations"))
    from core.extensions import db
    from core.managers import session_manager
    from core.models.base_game import get_game_model
    Game = get_game_model()
    print("baza po migracji: meczow", Game.query.count(), "| otwarta sesja:", session_manager.get_open_session())

    client = app.test_client()
    bledy = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if "GET" in rule.methods and not rule.arguments and not rule.rule.startswith(("/static", "/api/obs", "/api/hub", "/api/scraper", "/api/helper", "/api/gopro", "/api/servo", "/api/replay-export")):
            try:
                if client.get(rule.rule).status_code >= 500:
                    bledy.append(rule.rule)
            except Exception as e:
                bledy.append(f"{rule.rule}: {type(e).__name__}")
    print("test dymny tras GET na prawdziwych danych:", "OK" if not bledy else f"BLEDY {bledy}")

print(f"\nGotowa baza testowa: {dst}")
print("Uruchomienie modulu na tej bazie (po sprawdzeniu, ze porty 8080 i 8081 sa wolne i wersja transmisyjna nie dziala):")
print(f'  set DATABASE_URL=sqlite:///{dst.as_posix()}  &&  modules\\.venv\\Scripts\\python.exe modules\\{"nalf" if module == "futsal_nalf" else "garbarnia"}.py')
sys.exit(1 if bledy else 0)
