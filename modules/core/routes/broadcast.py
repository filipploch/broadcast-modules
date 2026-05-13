"""
core.routes.broadcast — trasy wspólne dla wszystkich modułów.

Obsługuje: timer UI, sterowanie okresami, sekwencje, nagrywanie,
           API statusu i ustawień.

Każdy moduł rejestruje te trasy przez:
    from core.routes import broadcast as core_broadcast
    core_broadcast.register_routes(app)
"""
from flask import (render_template, jsonify, current_app,
                   flash, redirect, url_for, request)
from core.managers.season_manager import SeasonManager
from core.managers.league_manager import LeagueManager
from core.managers.game_manager import GameManager
from core.managers.camera_manager import CameraManager
from core.managers.game_camera_manager import GameCameraManager
from core.extensions import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

season_manager = SeasonManager()
league_manager = LeagueManager()
game_manager = GameManager()

def _get_team():
    from core.models.base_team import get_team_model
    return get_team_model()

def _get_player():
    from core.models.base_player import get_player_model
    return get_player_model()

def _get_settings():
    from core.models.base_settings import get_settings_model
    return get_settings_model()

def _get_game():
    from core.models.base_game import get_game_model
    return get_game_model()

def _get_period():
    from core.models.base_period import get_period_model
    return get_period_model()


def register_routes(app, exclude=None):
    exclude = exclude or set()
    """Rejestruje wspólne trasy w instancji Flask aplikacji."""

    @app.route('/api/status')
    def api_status():
        return jsonify({
            'status': 'running',
            'module_id': current_app.config['MODULE_ID']
        })

    @app.route('/api/scoreboard-state', methods=['GET', 'POST'])
    def get_scoreboard_state():
        from core.models.base_settings import get_settings_model
        Settings = get_settings_model()
        from datetime import datetime
        settings = Settings.query.get(1)
        if not settings:
            settings = Settings(id=1, is_scoreboard_reversed=False)
            db.session.add(settings)
            db.session.commit()
        if request.method == 'POST':
            data = request.get_json()
            settings.is_scoreboard_reversed = data.get('is_reversed', False)
            settings.updated_at = datetime.utcnow()
            db.session.add(settings)
            db.session.commit()
            return jsonify({'success': True, 'is_reversed': settings.is_scoreboard_reversed})
        return jsonify({'is_reversed': settings.is_scoreboard_reversed})

    @app.route('/api/settings/current-timers')
    def api_current_timers():
        from core.models.base_settings import get_settings_model
        Settings = get_settings_model()
        timers = Settings.get_current_timers()
        return jsonify(timers)

    @app.route('/api/settings/current-timers/clear', methods=['POST'])
    def api_clear_current_timers():
        from core.models.base_settings import get_settings_model
        Settings = get_settings_model()
        Settings.clear_timers()
        return jsonify({'success': True, 'message': 'Timers cleared'})

    @app.route('/api/replay-export/current', methods=['POST'])
    def api_replay_export_current():
        from core.managers import get_replay_export_manager
        try:
            mgr = get_replay_export_manager()
            result = mgr.export_current_game()
            status = 200 if not result['errors'] else 207
            return jsonify(result), status
        except Exception as e:
            logger.error(f"api_replay_export_current: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/replay-export/<int:game_id>', methods=['POST'])
    def api_replay_export_run(game_id):
        from core.managers import get_replay_export_manager
        try:
            mgr = get_replay_export_manager()
            result = mgr.export_game(game_id)
            status = 200 if not result['errors'] else 207
            return jsonify(result), status
        except Exception as e:
            logger.error(f"api_replay_export_run({game_id}): {e}")
            return jsonify({'game_id': game_id, 'error': str(e)}), 500
        

    @app.route('/api/settings')
    def api_get_settings():
        """
        Get complete settings including current period, game and timers
    
        Used by timer recovery system to check what timers should be running
        after crash/restart.
    
        Returns JSON:
        {
            "current_season_id": int or null,
            "current_game_id": int or null,
            "current_period_id": int or null,
            "current_timers": {
                "main": {
                    "timer_id": "main-p1",
                    "state": "running",
                    "initial_time": 0,
                    "limit": 1200000,
                    ...
                } or null,
                "penalties": [
                    {
                        "timer_id": "penalty-1",
                        "state": "running",
                        ...
                    }
                ]
            },
            "period": {
                "id": int,
                "description": str,
                "main_timer_name": str,
                "initial_time": int,
                "limit": int,
                "pause_at_limit": bool,
                "status": int
            } or null,
            "game": {
                "id": int
            } or null
        }
        """
    
    
        Game = _get_game()
        Settings = _get_settings()
        Period = _get_period()
    
        settings = Settings.get_settings()
        current_timers = settings.get_current_timers()
    
        # Get period details if exists
        period_data = None
        if settings.current_period_id:
            period = Period.query.get(settings.current_period_id)
            if period:
                period_data = {
                    "id": period.id,
                    "description": period.description,
                    "period_order": period.period_order,
                    "main_timer_name": period.main_timer_name,
                    "initial_time": period.initial_time,
                    "limit": period.limit,
                    "pause_at_limit": period.pause_at_limit,
                    "status": period.status
                }
    
        # Get game details if exists
        game_data = None
        if settings.current_game_id:
            game = Game.query.get(settings.current_game_id)
            if game:
                game_data = {
                    "id": game.id,
                    # Add other game fields as needed
                }

        is_reversed = False
        if settings.is_scoreboard_reversed:
            is_reversed = True
    
        return jsonify({
            "current_season_id": settings.current_season_id,
            "current_game_id": settings.current_game_id,
            "current_period_id": settings.current_period_id,
            "current_timers": current_timers,
            "period": period_data,
            "game": game_data,
            "is_reversed": is_reversed
        })