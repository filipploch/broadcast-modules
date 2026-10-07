"""Uruchamia modul na bazie testowej BEZ kopiowania plikow do overlayow (probe na sucho E1):
    set DATABASE_URL=sqlite:///... && set BM_REQUIRED_PLUGINS=timer-plugin && python tests/modules/dry_run_module.py futsal_nalf
"""
import os, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
module = sys.argv[1] if len(sys.argv) > 1 else "futsal_nalf"
sys.path[:0] = [str(REPO / "modules" / module), str(REPO / "modules")]
os.chdir(REPO / "modules" / module)
from app import create_app
from core.extensions import socketio

app = create_app("development")
socketio.run(app, host="127.0.0.1", port=app.config["APP_PORT"], debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
