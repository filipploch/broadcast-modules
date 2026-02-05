"""Application entry point"""
import sys
import signal
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
