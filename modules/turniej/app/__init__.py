"""Application factory — moduł turniej."""
import logging
import threading

from flask import Flask
from pathlib import Path


_EVENTS_SEED = [
    dict(name='Bramka',           short_name='GOL',  is_reported=True,  image_path='static/images/overlay/futsal/goal.png',        filter_class='goal',        color='#69ffa7', player_from_opponent=False),
    dict(name='Bramka Samobójcza',short_name='SAM',  is_reported=True,  image_path='static/images/overlay/futsal/own_goal.png',     filter_class='goal',        color='#f88f8f', player_from_opponent=True),
    dict(name='Obrona',           short_name='OBR',  is_reported=False, image_path=None,                                            filter_class='save',        color='#8e44ad', player_from_opponent=True),
    dict(name='Pudło',            short_name='PUD',  is_reported=False, image_path=None,                                            filter_class='miss',        color='#37d3ce', player_from_opponent=False),
    dict(name='Faul',             short_name='FAUL', is_reported=False, image_path=None,                                            filter_class='foul',        color='#f77e1a', player_from_opponent=False),
    dict(name='Żółta Kartka',     short_name='ŻK',   is_reported=True,  image_path='static/images/overlay/futsal/yellow_card.png',  filter_class='yellow_card', color='#f3ec12', player_from_opponent=False),
    dict(name='Czerwona Kartka',  short_name='CZK',  is_reported=True,  image_path='static/images/overlay/futsal/red_card.png',     filter_class='red_card',    color='#ff1900', player_from_opponent=False),
    dict(name='VAR',              short_name='VAR',  is_reported=False, image_path=None,                                            filter_class='var',         color='#5454e2', player_from_opponent=False),
    dict(name='HAHAHA',           short_name='XD',   is_reported=False, image_path=None,                                            filter_class=None,          color='#7c7c7c', player_from_opponent=False),
    dict(name='Bum',              short_name='BUM',  is_reported=False, image_path=None,                                            filter_class=None,          color='#3c3c3c', player_from_opponent=False),
]


def _seed_events(db, app):
    try:
        from app.models.event import Event
        if Event.query.count() == 0:
            for row in _EVENTS_SEED:
                db.session.add(Event(**row))
            db.session.commit()
            app.logger.info(f"✅ Seeded {len(_EVENTS_SEED)} events")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Event seeding failed: {e}")


def _reset_schema_if_stale(db, app):
    """Usuwa wszystkie tabele jeśli schemat pochodzi ze starej wersji (zawiera team_url)."""
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if inspector.has_table('teams'):
            cols = {c['name'] for c in inspector.get_columns('teams')}
            if 'team_url' in cols or 'foreign_id' in cols:
                app.logger.warning("⚠️  Stary schemat DB wykryty — reset tabel")
                db.drop_all()
    except Exception as e:
        app.logger.error(f"Schema check failed: {e}")


def create_app(config_name='default'):

    template_dir = Path(__file__).resolve().parent.parent.parent/'templates'
    static_dir = Path(__file__).resolve().parent.parent.parent/'static'

    app = Flask(__name__,
            template_folder=str(template_dir),
            static_folder=str(static_dir))

    from config import config
    app.config.from_object(config[config_name])

    logging.basicConfig(
        level=logging.DEBUG if app.debug else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    from core.extensions import db, socketio
    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    with app.app_context():
        from app.models import (
            Season, Stadium,
            Camera, Commentator, Referee,
            Event, EventCamera,
            GameEvent, GameCamera, GameCommentator, GameReferee,
        )
        from app.models import (
            Settings, Period, GamePlayer, GameTimer,
            League, LeagueTeam, Team, Game, Player,
            Banner, BackgroundImage,
        )

        _reset_schema_if_stale(db, app)
        db.create_all()
        app.logger.info("✅ Database tables created/verified")
        _seed_events(db, app)

    with app.app_context():
        from core.routes import broadcast as core_broadcast
        from core.routes import routes_crud as routes_crud
        from core.socketio_events import base as core_events

        core_broadcast.register_routes(app)
        routes_crud.register_routes(app,
            exclude={'/game-setup'},
            team_manager=None
        )
        core_events.register_events(socketio)

        from app.routes import specific_routes as specific_routes
        from app.socketio_events import specific_socketio_events as specific_events
        specific_routes.register_routes(app)
        specific_events.register_events(socketio)

        @app.before_request
        def redirect_if_no_data():
            from flask import request, redirect, url_for
            control_paths = {'/', '/game-period-choice', '/game-setup'}
            if request.path not in control_paths:
                return
            try:
                from app.models.season import Season
                if Season.query.count() == 0:
                    return redirect(url_for('common_data'))
            except Exception:
                pass

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
                    'module_name':       app.config.get('MODULE_NAME', ''),
                }
            except Exception:
                return {'broadcast_game_id': None, 'season': None, 'module_name': ''}

    def init_managers():
        with app.app_context():
            from app.managers import initialize_all_managers
            initialize_all_managers(app)

    threading.Thread(target=init_managers, daemon=True).start()

    app.logger.info("✅ Application initialized")
    return app
