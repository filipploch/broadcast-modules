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

def _get_game_event_data(game_event_id, new_event_type_id=None):
    from core.managers.game_event_manager import GameEventManager
    from core.managers.game_manager import GameManager

    gem        = GameEventManager()
    game_event = gem.get_game_event_by_id(game_event_id)
    game_data  = GameManager().get_game_by_id(game_event.game_id)

    if new_event_type_id == 3 and game_event.event_id in [1, 2, 4, 5, 6, 7]:
        game_event.team_id  = (game_data.away_team_id
                                if game_event.team_id == game_data.home_team_id
                                else game_data.home_team_id)
        game_event.event_id = new_event_type_id
    elif new_event_type_id in [1, 2, 4, 5, 6, 7] and game_event.event_id == 3:
        game_event.team_id  = (game_data.away_team_id
                                if game_event.team_id == game_data.home_team_id
                                else game_data.home_team_id)
        game_event.event_id = new_event_type_id
    elif new_event_type_id:
        game_event.event_id = new_event_type_id

    team_squad = None
    if game_event.event_id in [1, 4, 5, 6, 7]:
        team_squad = ('home_team_squad'
                        if game_event.team_id == game_data.home_team_id
                        else 'away_team_squad')
    elif game_event.event_id in [2, 3]:
        team_squad = ('away_team_squad'
                        if game_event.team_id == game_data.home_team_id
                        else 'home_team_squad')

    return {
        'team_squad': game_data.to_dict()[team_squad] if team_squad else None,
        'game_event': game_event.to_dict(),
    }

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

    # ── Filters ───────────────────────────────────────────────────────────────

    @socketio.on('enable_scene_filter')
    def handle_enable_scene_filter(data):
        from core.managers import get_obs_ws_manager
        obs_ws_manager = get_obs_ws_manager()
        source_name = data.get('source_name')
        filter_name = data.get('filter_name')
        filter_state = data.get('filter_state')
        obs_ws_manager.enable_source_filter(source_name, filter_name, filter_state)

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
                    result = mgr.export_game(game_id) if game_id else mgr.export_current_game()
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

    # ── Send to overlay ───────────────────────────────────────────────────────

    @socketio.on('send_to_overlay')
    def handle_send_to_overlay(data):
        """Przekazuje dowolny sygnał bezpośrednio do overlay przez hub.

        data = { 'type': str, 'payload': any }
        """
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if hub_client:
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to':   'stream-overlay',
                'type': data.get('type'),
                'payload': data.get('payload', {}),
            })

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

    @socketio.on('replay_control')
    def handle_replay_control(data):
        """
        Przekazuje polecenia sterowania powtórką do replay-plugin przez hub.

        Obsługiwane typy (data.type):
            pause        — pauza
            resume       — wznów
            stop         — zatrzymaj
            speed        — zmień prędkość (data.speed: float)
            frame_fwd    — krok o klatkę do przodu (wymaga pauzy)
            frame_back   — krok o klatkę do tyłu (wymaga pauzy)
            cancel_timer — cancel_time_dependent_replay_end
            end          — end_replay (tylko w trybie ręcznym)
        """
        from core.managers import get_hub_client
        hub = get_hub_client()
        if not hub:
            return

        cmd_type = data.get('type')
        type_to_signal = {
            'pause':        'replay_pause',
            'resume':       'replay_resume',
            'stop':         'replay_stop',
            'speed':        'replay_speed',
            'frame_fwd':    'replay_frame_forward',
            'frame_back':   'replay_frame_back',
            'cancel_timer': 'cancel_time_dependent_replay_end',
            'end':          'end_replay',
        }
        signal = type_to_signal.get(cmd_type)
        if not signal:
            current_app.logger.warning(f'[replay_control] Nieznany typ: {cmd_type}')
            return

        payload = {}
        if cmd_type == 'speed':
            payload['speed'] = data.get('speed', 0.9)

        hub.send({
            'from':    current_app.config.get('MODULE_ID', 'main-module'),
            'to':      'replay-plugin',
            'type':    signal,
            'payload': payload,
        })
        current_app.logger.info(f'[replay_control] {cmd_type} → {signal}')


def handle_ui_monitor_content(data, extra_handler=None):
    """
    Wspólna logika request_ui_monitor_content.
    extra_handler — opcjonalna funkcja z modułu obsługująca content_type
    specyficzne dla modułu. Zwraca dict lub None.
    """
    content_type = data.get('type')
    # Wspólne content_type obsługiwane przez core
    result = _handle_core_content(content_type, data)

    # Jeśli core nie obsłużył — przekaż do modułu
    if result is None and extra_handler:
        result = extra_handler(content_type, data)

    if result is None:
        result = {'error': f'Unknown content_type: {content_type}'}

    from core.extensions import socketio
    socketio.emit('show_ui_monitor_content', result)


def _handle_core_content(content_type, data):
    """Obsługuje content_type wspólne dla wszystkich modułów."""
    if content_type is None:
        return {'content_type': None}

    if content_type == 'events':
        from core.managers.event_manager import EventManager
        from core.managers.game_event_manager import GameEventManager
        from core.managers.game_manager import GameManager
        Settings = _get_settings()
        settings = Settings.get_settings()
        game = GameManager().get_game_by_id(settings.current_game_id)
        
        gem        = GameEventManager()
        event_mgr  = EventManager()

        events_types = [e.to_dict() for e in event_mgr.get_all_events()]
        game_events  = []
        for period in game.get_periods_list():
            period_events = gem.get_events_for_game(settings.current_game_id,
                                                    period_id=period.id)
            if period_events:
                game_events.extend(e.to_dict() for e in period_events)
                game_events.append(period.description)

        return {
            'content_type': 'events',
            'events_types': events_types,
            'game_events':  game_events,
        }

    elif content_type == 'edit_event':
        from core.managers.event_manager import EventManager
        Settings = _get_settings()

        payload      = data.get('payload', {})
        game_event_d = _get_game_event_data(payload['game_event_id'])
        events_types = [
            e.to_dict() for e in EventManager().get_all_events()
            if e.filter_class
        ]
        return {
            'content_type':          'edit_event',
            'events_types':          events_types,
            'is_scoreboard_reversed': bool(Settings.get_settings().is_scoreboard_reversed),
            'team_squad':            game_event_d['team_squad'],
            'game_event':            game_event_d['game_event'],
        }

    elif content_type == 'get_event_squad':
        payload      = data.get('payload', {})
        game_event_d = _get_game_event_data(
            payload['game_event_id'], payload.get('new_event_type_id')
        )
        return {
            'content_type': 'get_event_squad',
            'game_event':   game_event_d['game_event'],
            'team_squad':   game_event_d['team_squad'],
        }
    elif content_type == 'games':
        from core.managers.game_manager import GameManager
        from core.managers.league_manager import LeagueManager
        from core.models.base_settings import get_settings_model
        from datetime import date

        payload    = data.get('payload') or {}
        league_id  = payload.get('league_id')
        date_from  = payload.get('date_from', date.today().isoformat())
        date_to    = payload.get('date_to', date_from)

        # Domyślnie: liga aktualnie transmitowanego meczu
        if league_id is None:
            Settings = get_settings_model()
            settings = Settings.get_settings()
            current_game = GameManager().get_game_by_id(settings.current_game_id)
            league_id = current_game.league_id if current_game else None

        from core.extensions import db
        from core.models.base_game import get_game_model
        Game = get_game_model()

        leagues = LeagueManager().get_all_leagues()

        # Dołącz max_group_nr per liga (potrzebne do standings fetch w JS)
        leagues_data = []
        for l in leagues:
            d = l.to_dict()
            max_grp = (
                db.session.query(db.func.max(Game.group_nr))
                .filter(Game.league_id == l.id)
                .scalar()
            )
            d['max_group_nr'] = max_grp or 1
            leagues_data.append(d)

        games = GameManager().get_all_games(
            league_id=league_id,
            date_from=date_from,
            date_to=date_to,
        ) if league_id else []

        return {
            'content_type': 'games',
            'league_id':    league_id,
            'date_from':    date_from,
            'date_to':      date_to,
            'leagues':      leagues_data,
            'games':        [g.to_dict() for g in games],
        }

    return None  # nieznany — przekaż do modułu

