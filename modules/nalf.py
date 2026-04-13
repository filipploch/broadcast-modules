"""Entry point dla futsal-nalf — uruchamiany z katalogu broadcast-modules/."""
import sys
import signal
from pathlib import Path
import shutil

# broadcast-modules/ — żeby działało "import core"
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# broadcast-modules/modules/futsal_nalf/ — żeby działało "from app import ..."
# i "from config import config"
MODULE_DIR = ROOT / 'modules' / 'futsal_nalf'
sys.path.insert(0, str(MODULE_DIR))

from app import create_app
from app.extensions import socketio

app = create_app('development')


def shutdown_handler(signum=None, frame=None):
    print("\n Shutting down...")
    with app.app_context():
        from app.managers import shutdown_all_managers
        shutdown_all_managers()
    print(" Shutdown complete")
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    js_src = ROOT / app.config['SPECIFIC_JS_FILE']
    js_dst = ROOT / app.config['HUB_JS_DIR']
    css_src = ROOT / app.config['SPECIFIC_CSS_FILE']
    css_dst = ROOT / app.config['HUB_CSS_DIR']

    shutil.copy(js_src, js_dst)
    shutil.copy(css_src, css_dst)

    print("=" * 60)
    print(f" {app.config['MODULE_NAME']}")
    print(f" http://{app.config['APP_HOST']}:{app.config['APP_PORT']}")
    print("=" * 60)

    try:
        socketio.run(
            app,
            host=app.config['APP_HOST'],
            port=app.config['APP_PORT'],
            debug=app.config['DEBUG'],
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        shutdown_handler()
