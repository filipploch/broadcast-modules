"""
core.socketio_events.base — wspólne handlery SocketIO dla wszystkich modułów.

Obsługuje: connect/disconnect, timer control, OBS, recorder,
           sekwencje, replay export, scoreboard reverse.

Rejestracja:
    from core.socketio_events import base as core_events
    core_events.register_events(socketio)
"""
import logging
from flask import current_app

logger = logging.getLogger(__name__)

def _get_settings():
    from core.models.base_settings import get_settings_model
    return get_settings_model()

def register_events(socketio):
    """Rejestruje wspólne handlery SocketIO."""

    @socketio.on('connect')
    def handle_connect():
        from flask_socketio import emit
        logger.info('Client connected')
        socketio.emit('connected', {'status': 'ok'})

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('Client disconnected')

    # ── Timer ─────────────────────────────────────────────────────────────────

    @socketio.on('timer_start')
    def handle_timer_start(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.start_timer(timer_id):
            socketio.emit('timer_started', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to start timer: {timer_id}'})

    @socketio.on('timer_pause')
    def handle_timer_pause(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.pause_timer(timer_id):
            socketio.emit('timer_paused', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to pause timer: {timer_id}'})

    @socketio.on('timer_resume')
    def handle_timer_resume(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.resume_timer(timer_id):
            socketio.emit('timer_resumed', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to resume timer: {timer_id}'})

    @socketio.on('timer_reset')
    def handle_timer_reset(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.reset_timer(timer_id):
            socketio.emit('timer_reset', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to reset timer: {timer_id}'})

    @socketio.on('timer_remove')
    def handle_timer_remove(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.remove_timer(timer_id):
            socketio.emit('timer_removed', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to remove timer: {timer_id}'})

    @socketio.on('timer_adjust')
    def handle_timer_adjust(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        delta = data.get('delta', 0)
        tm.adjust_time(timer_id, delta)

    @socketio.on('timer_set_time')
    def handle_timer_set_time(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id     = data.get('timer_id')
        elapsed_time = data.get('elapsed_time', 0)
        if tm.set_elapsed_time(timer_id, elapsed_time):
            socketio.emit('timer_time_set', {'timer_id': timer_id, 'elapsed_time': elapsed_time},
                 broadcast=True)

    @socketio.on('timers_get_all')
    def handle_timers_get_all(data):
        from core.managers import get_timer_manager
        get_timer_manager().get_all_timers()

    # ── Recording ─────────────────────────────────────────────────────────────

    @socketio.on('start_recording')
    def handle_start_recording(data):
        from core.managers import get_hub_client
        from core.managers import get_recorder_manager
        from flask_socketio import emit
        hub_client = get_hub_client()
        if hub_client:
            from core.sequences.steps import start_recording
            step = start_recording()
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to': step['target'],
                'type': step['action'],
                'payload': step['payload']
            })

    @socketio.on('stop_recording')
    def handle_stop_recording(data):
        from core.managers import get_hub_client
        from flask_socketio import emit
        hub_client = get_hub_client()
        if hub_client:
            from core.sequences.steps import stop_recording
            step = stop_recording()
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to': step['target'],
                'type': step['action'],
                'payload': step['payload']
            })

    @socketio.on('get_obs_ws_connection')
    def handle_get_obs_ws_connection():
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if hub_client:
            hub_client.send_to_plugin('obs-ws-plugin', 'obs_command', {
                'requestType': 'GetVersion',
                'requestData': {},
                'request_id': 'get-websocket-connection'
            })

    # ── Sequences ─────────────────────────────────────────────────────────────

    @socketio.on('trigger_sequence')
    def handle_trigger_sequence(data):
        from flask_socketio import emit
        from core.managers import get_sequence_manager
        sm          = get_sequence_manager()
        sequence_id = sm.trigger(data['sequence'], data.get('context', {}))
        socketio.emit('sequence_started', {'sequence_id': sequence_id})

    @socketio.on('stop_sequence')
    def handle_stop_sequence(data):
        from flask_socketio import emit
        from core.managers import get_sequence_manager
        sm          = get_sequence_manager()
        sequence_id = data.get('sequence_id')
        if sequence_id:
            sm.stop(sequence_id)
            socketio.emit('sequence_stopped', {'sequence_id': sequence_id})
        else:
            sm.stop_all(data.get('sequence'))
            socketio.emit('all_sequences_stopped', {})

    # ── Replay export ─────────────────────────────────────────────────────────

    @socketio.on('replay_export_run')
    def handle_replay_export_run(data):
        import threading
        from flask_socketio import emit
        game_id = data.get('game_id')
        app     = current_app._get_current_object()

        def _run():
            with app.app_context():
                try:
                    from core.managers import get_replay_export_manager
                    mgr    = get_replay_export_manager()
                    result = mgr.export_game(game_id) if game_id                              else mgr.export_current_game()
                    from core.extensions import socketio as _sio
                    _sio.emit('replay_export_done', result)
                except Exception as e:
                    app.logger.error(f'replay_export_run error: {e}')
                    from core.extensions import socketio as _sio
                    _sio.emit('replay_export_done', {
                        'game_id': game_id, 'folder': None,
                        'files_saved': 0, 'errors': [str(e)]
                    })

        threading.Thread(target=_run, daemon=True).start()
        socketio.emit('replay_export_started', {'game_id': game_id})

    # ── Scoreboard reverse ────────────────────────────────────────────────────

    @socketio.on('reverse_scoreboard')
    def handle_reverse_scoreboard(data):
        Settings = _get_settings()
        from core.extensions import socketio as _sio
        settings = Settings.get_settings()
        settings.is_scoreboard_reversed = not settings.is_scoreboard_reversed
        from core.extensions import db
        db.session.commit()
        _sio.emit('scoreboard_reversed', {'is_reversed': settings.is_scoreboard_reversed})

    @socketio.on('set_reversed')
    def handle_set_reversed(data):
        Settings = _get_settings()
        from core.extensions import socketio as _sio
        settings = Settings.get_settings()
        settings.is_scoreboard_reversed = data.get('is_reversed', False)
        from core.extensions import db
        db.session.commit()
        _sio.emit('scoreboard_reversed', {'is_reversed': settings.is_scoreboard_reversed})

    # ── Show overlay ──────────────────────────────────────────────────────────

    @socketio.on('show_overlay_container')
    def handle_show_overlay_container(data):
        from core.managers import get_hub_client
        from core.sequences.steps import show_overlay_container
        hub_client = get_hub_client()
        if hub_client:
            step = show_overlay_container(data)
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to': step['target'],
                'type': step['action'],
                'payload': step['payload']
            })
