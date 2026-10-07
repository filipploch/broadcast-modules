"""Proba migracji na kopii lokalnej bazy modulu: upgrade do head, downgrade o jedna wersje, upgrade. Nie dotyka oryginalu.

    python tests/modules/probe_migrations.py [futsal_nalf|garbarnia]
"""
import os, pathlib, shutil, sqlite3, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
module = sys.argv[1] if len(sys.argv) > 1 else "futsal_nalf"
tmp = pathlib.Path(tempfile.mkdtemp(prefix="bm-mig-"))
shutil.copy(REPO / "modules" / module / "instance" / "database.db", tmp / "copy.db")
os.environ["BM_TEST_DATABASE_URL"] = "sqlite:///" + (tmp / "copy.db").as_posix()
sys.path[:0] = [str(REPO / "modules" / module), str(REPO / "modules")]
os.chdir(REPO / "modules" / module)
from app import create_app
import flask_migrate

app = create_app("testing")
def state():
    c = sqlite3.connect(tmp / "copy.db")
    v = c.execute("select version_num from alembic_version").fetchall()
    t = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    c.close()
    return v, t
with app.app_context():
    print("start:", state()[0])
    flask_migrate.upgrade(directory=str(REPO / "modules" / module / "migrations"))
    v, t = state(); print("po upgrade:", v, "tabele sesji:", {"broadcast_sessions", "session_games"} <= t)
    ok = {"broadcast_sessions", "session_games"} <= t
    flask_migrate.downgrade(directory=str(REPO / "modules" / module / "migrations"), revision="-1")
    v, t = state(); print("po downgrade:", v, "tabele sesji:", {"broadcast_sessions", "session_games"} & t)
    ok &= not ({"broadcast_sessions", "session_games"} & t)
    flask_migrate.upgrade(directory=str(REPO / "modules" / module / "migrations"))
    v, t = state(); print("po ponownym upgrade:", v)
    ok &= {"broadcast_sessions", "session_games"} <= t
print("MIGRACJA:", "OK" if ok else "BLAD")
sys.exit(0 if ok else 1)
