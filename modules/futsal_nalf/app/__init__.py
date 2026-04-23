"""Application factory — moduł futsal-nalf."""
import logging
import threading

from flask import Flask
from pathlib import Path


def create_app(config_name='default'):

    template_dir = Path(__file__).resolve().parent.parent.parent/'templates'
    static_dir = Path(__file__).resolve().parent.parent.parent/'static'

    app = Flask(__name__, 
            template_folder=str(template_dir),
            static_folder=str(static_dir))

    # Konfiguracja
    from config import config
    app.config.from_object(config[config_name])

    # Logging
    logging.basicConfig(
        level=logging.DEBUG if app.debug else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Rozszerzenia — używamy instancji z core
    from core.extensions import db, socketio
    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    # Tworzenie tabel — importy modeli muszą być przed db.create_all()
    with app.app_context():
        # Modele core (wspólne tabele)
        # Modele core — tabele współdzielone (bez tych które moduł nadpisuje)
        from app.models import (
            Season, Stadium,
            Camera, Commentator, Referee,
            Event, EventCamera,
            GameEvent, GameCamera, GameCommentator, GameReferee,
        )
        # Modele futsal-nalf — nadpisują lub rozszerzają klasy bazowe core
        from app.models import (
            Settings, Period, GamePlayer, GameTimer,
            League, LeagueTeam, Team, Game, Player,
            Shootout, ShootoutKick,
        )

        db.create_all()
        app.logger.info("✅ Database tables created/verified")

    # Rejestracja tras i zdarzeń SocketIO
    with app.app_context():
        # Trasy i eventy z core
        from core.routes import broadcast as core_broadcast
        from core.routes import routes_crud as routes_crud
        from core.socketio_events import base as core_events
        core_broadcast.register_routes(app)
        routes_crud.register_routes(app, exclude={
            '/game-setup'
            })
        core_events.register_events(socketio)

        # Trasy i eventy specyficzne dla modułu
        from app.routes import specific_routes as specific_routes
        from app.socketio_events import specific_socketio_events as specific_events
        specific_routes.register_routes(app)
        specific_events.register_events(socketio)
        print("REGISTERED ROUTES:", [r.endpoint for r in app.url_map.iter_rules()])

        @app.context_processor
        def inject_global_context():
            try:
                from app.models.settings import Settings
                from app.models.season import Season
                settings = Settings.get_settings()
                season = Season.query.get(settings.current_season_id) \
                         if settings.current_season_id else None
                return {
                    'broadcast_game_id': settings.current_game_id,
                    'season': season,
                    'timer_desc':        app.config.get('TIMER_DESC', True),
                }
            except Exception:
                return {'broadcast_game_id': None, 'season': None}

    # Inicjalizacja managerów w tle
    def init_managers():
        with app.app_context():
            from app.managers import initialize_all_managers
            initialize_all_managers(app)

    threading.Thread(target=init_managers, daemon=True).start()

    app.logger.info("✅ Application initialized")
    return app
