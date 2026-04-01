"""Application factory - UPDATED VERSION"""
from flask import Flask, Blueprint
import logging
# from app.app_routes import app_bp



def create_app(config_name='default'):
    app = Flask(__name__)

    # Load configuration
    from config import config
    app.config.from_object(config[config_name])

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if app.debug else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Initialize extensions
    from app.extensions import db, socketio
    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    # Import models and create tables
    with app.app_context():
        # Import all models so SQLAlchemy knows about them
        from app.models import (
            # Plugin,
            Settings,
            Season,
            League,
            Team,
            LeagueTeam,
            Stadium,
            Game,
            GameTimer,
        )

        # Create tables
        db.create_all()

        app.logger.info("✅ Database tables created/verified")

    # Register routes and socketio events
    with app.app_context():

        from app import routes, socketio_events

        @app.context_processor
        def inject_global_context():
            """Inject common data into all templates"""
            try:
                from app.models.settings import Settings
                from app.models.season import Season
                settings = Settings.get_settings()
                season = Season.query.get(settings.current_season_id) if settings.current_season_id else None
                return {
                    'broadcast_game_id': settings.current_game_id,
                    'season': season,
                }
            except Exception:
                return {
                    'broadcast_game_id': None,
                    'season': None,
                }

    # Initialize managers in background thread
    import threading

    def init_managers():
        with app.app_context():
            from app.managers import initialize_all_managers
            initialize_all_managers(app)

    thread = threading.Thread(target=init_managers, daemon=True)
    thread.start()

    app.logger.info("✅ Application initialized")

    return app
