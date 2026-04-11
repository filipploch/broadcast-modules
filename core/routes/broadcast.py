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
from core.extensions import db
import logging

logger = logging.getLogger(__name__)


def register_routes(app):
    """Rejestruje wspólne trasy w instancji Flask aplikacji."""

    @app.route('/api/status')
    def api_status():
        return jsonify({
            'status': 'running',
            'module_id': current_app.config['MODULE_ID']
        })

    @app.route('/api/scoreboard-state', methods=['GET', 'POST'])
    def get_scoreboard_state():
        from core.models.settings import Settings
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
        from core.models.settings import Settings
        timers = Settings.get_current_timers()
        return jsonify(timers)

    @app.route('/api/settings/current-timers/clear', methods=['POST'])
    def api_clear_current_timers():
        from core.models.settings import Settings
        Settings.clear_timers()
        return jsonify({'success': True, 'message': 'Timers cleared'})

    # @app.route('/api/settings')
    # def api_get_settings():
    #     from core.models.settings import Settings
    #     from core.models.period import Period
    #     settings = Settings.get_settings()
    #     current_timers = settings.get_current_timers()
    #     period_data = None
    #     if settings.current_period_id:
    #         period = Period.query.get(settings.current_period_id)
    #         if period:
    #             period_data = {
    #                 "id": period.id,
    #                 "description": period.description,
    #                 "period_order": period.period_order,
    #                 "main_timer_name": period.main_timer_name,
    #                 "initial_time": period.initial_time,
    #                 "limit": period.limit,
    #                 "pause_at_limit": period.pause_at_limit,
    #                 "status": period.status
    #             }
    #     is_reversed = bool(settings.is_scoreboard_reversed)
    #     return jsonify({
    #         "current_season_id": settings.current_season_id,
    #         "current_game_id": settings.current_game_id,
    #         "current_period_id": settings.current_period_id,
    #         "current_timers": current_timers,
    #         "period": period_data,
    #         "is_reversed": is_reversed
    #     })

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
