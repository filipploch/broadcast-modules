"""
app.socketio_events.turniej — handlery SocketIO specyficzne dla turniej.
"""
import logging
from flask import current_app
from core.managers import (get_hub_client, get_timer_manager,
                           get_sequence_manager, get_recorder_manager)
from app.managers import GamePlayerManager, GameManager, PeriodManager, GameEventManager, TimerManager, EventManager
logger = logging.getLogger(__name__)


def _resolve_event_id(event_type: str) -> int:
    from app.models.event import Event
    event = Event.query.filter(Event.name.ilike(event_type)).first()
    if not event:
        raise ValueError(f"Nieznany typ zdarzenia: '{event_type}'")
    return event.id


def _get_timer_manager_or_error():
    from flask_socketio import emit
    tm = get_timer_manager()
    if not tm:
        emit('error', {'message': 'Timer manager not available'})
        return None
    return tm


def register_events(socketio):
    """Rejestruje handlery SocketIO specyficzne dla turniej."""

    @socketio.on('get_shootouts')
    def handle_get_shootout_data():
        from app.models.shootout import Shootout
        from app.models.settings import Settings
        settings = Settings.get_settings()
        if settings.current_shootout_id:
            s = Shootout.query.get(settings.current_shootout_id)
            if s:
                socketio.emit('response_get_shootouts', {'shootout': s.to_dict(), 'kicks': []})

    @socketio.on('get_game_teams')
    def handle_get_game_teams():
        from app.models.game_player import GamePlayer
        from app.models.settings import Settings
        settings = Settings.get_settings()
        current_game_id = settings.current_game_id
        game_manager = GameManager()
        game = game_manager.get_game_by_id(game_id=current_game_id)
        game_data = game.to_dict()
        game_player_manager = GamePlayerManager()
        home_team_id = game_data['home_team_id']
        away_team_id = game_data['away_team_id']
        home_players = [gp.to_squad_dict() for gp in game_player_manager.get_players_for_game(game_id=game.id, team_id=home_team_id)]
        away_players = [gp.to_squad_dict() for gp in game_player_manager.get_players_for_game(game_id=game.id, team_id=away_team_id)]

        socketio.emit('response_get_game_teams', {
            'game_data': game_data,
            'home_team_players': home_players,
            'away_team_players': away_players,
        })

    # =========================================================================
    # INITIAL DATA
    # =========================================================================

    @socketio.on('request_initial_data')
    def handle_request_initial_data():
        from app.models.settings import Settings
        from app.models.period import Period
        from app.models.game import Game

        settings    = Settings.get_settings()
        is_reversed = bool(settings.is_scoreboard_reversed)
        period      = Period.query.get(settings.current_period_id) if settings.current_period_id else None
        game_obj    = Game.query.get(period.game_id) if period else None
        game        = game_obj.to_dict() if game_obj else None

        timer_manager = get_timer_manager()
        main_gt = (
            timer_manager.get_active_main_timer(settings.current_period_id)
            if (timer_manager and period) else None
        )
        penalties = (
            timer_manager._get_penalties_dict(settings.current_period_id)
            if (timer_manager and period) else {'home': [], 'away': []}
        )

        hub_client = get_hub_client()
        if hub_client and game:
            hub_client.broadcast_to_class('overlay', 'game_data', game)

        if game:
            socketio.emit('initial_data', {
                'home_team_goals':   game['home_team_goals'],
                'away_team_goals':   game['away_team_goals'],
                'home_team_fouls':   game['home_team_fouls'],
                'away_team_fouls':   game['away_team_fouls'],
                'home_team_uniform': game['home_team_uniform'],
                'away_team_uniform': game['away_team_uniform'],
                'home_penalties':    penalties['home'],
                'away_penalties':    penalties['away'],
                'main_timer':        main_gt.to_dict() if main_gt else None,
                'is_reversed':       is_reversed,
            })

    # =========================================================================
    # UI MONITOR
    # =========================================================================

    @socketio.on('request_ui_monitor_content')
    def handle_request_ui_monitor_content(data):
        from core.socketio_events.base import handle_ui_monitor_content
        handle_ui_monitor_content(data)

    @socketio.on('add_team_event')
    def handle_add_team_event(data):
        team_type = data.get('team_type')
        event_name = data.get('event_name')
        socketio.emit('team_event_added', {'team_type': team_type, 'event_name': event_name})

    # =========================================================================
    # OVERLAY / RECORD STATUS
    # =========================================================================

    @socketio.on('get_record_status')
    def handle_get_record_status():
        hub_client = get_hub_client()
        if hub_client:
            from datetime import datetime
            from core.managers.game_camera_manager import GameCameraManager
            from app.models.settings import Settings
            settings = Settings.get_settings()
            cameras = (GameCameraManager().get_cameras_dict_for_game(settings.current_game_id)
                       if settings and settings.current_game_id else
                       {'camera1': False, 'camera2': False, 'camera3': False, 'camera4': False})
            hub_client.broadcast(msg_type='recording_command', payload={
                'requestType': 'GetRecordStatus',
                'requestData': {},
                'request_id': f'rec-status-{datetime.now()}',
                'cameras': cameras,
            })

    # =========================================================================
    # TIMERS
    # =========================================================================

    @socketio.on('timer_create')
    def handle_timer_create(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return

        timer_id   = data.get('timer_id')
        timer_type = data.get('timer_type', 'independent')
        keys       = ('parent_id', 'limit', 'pause_at_limit', 'initial_time',
                      'update_interval_ms', 'metadata')
        kwargs     = {k: data[k] for k in keys if k in data}

        if not tm.create_timer(timer_id, timer_type, **kwargs):
            socketio.emit('error', {'message': f'Failed to create timer {timer_id}'})

    @socketio.on('match_timer_create')
    def handle_game_timer_create(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return

        game_id          = data.get('game_id')
        duration_minutes = data.get('duration_minutes', 15)
        timer_id         = tm.create_game_timer(game_id, duration_minutes)

        socketio.emit('match_timer_created', {'game_id': game_id, 'timer_id': timer_id},
             broadcast=True)

    @socketio.on('penalty_timer_create')
    def handle_penalty_timer_create(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return

        from app.models.settings import Settings
        game_id          = Settings.get_settings().current_game_id
        game_timer_id    = data.get('game_timer_id')
        team             = data.get('team', 'home')
        team_name        = data.get('team_name', '')
        duration_minutes = data.get('duration_minutes', 2)

        active = tm.get_active_penalties_by_team(game_id, team)
        if len(active) >= 2:
            socketio.emit('error', {'message': f'Max 2 active penalties per team'})
            return

        import time
        penalty_timer_id = f'penalty_{team}_{int(time.time() * 1000)}'

        tm.create_timer(
            timer_id=penalty_timer_id,
            timer_type='dependent',
            parent_id=game_timer_id,
            initial_time=0,
            limit=duration_minutes * 60_000,
            pause_at_limit=True,
            metadata={
                'team': team, 'team_name': team_name,
                'timer_class': 'penalty', 'duration_minutes': duration_minutes,
            },
        )

    # =========================================================================
    # GAME SCORE / EVENTS
    # =========================================================================

    @socketio.on('change_game_value')
    def handle_change_game_value(data):
        from app.models.settings import Settings
        from app.models.game import Game

        period_manager    = PeriodManager()
        current_game_id   = Settings.get_settings().current_game_id
        current_period_id = period_manager.get_current_period(current_game_id).id
        team_type  = data.get('team_type')
        value_type = data.get('value_type')
        value      = data.get('value')

        period = None
        if value_type == 'score':
            period = period_manager.increment_period_goal(current_period_id, team_type, value)
        elif value_type == 'fouls':
            period = period_manager.increment_period_foul(current_period_id, team_type, value)

        if period:
            game = Game.query.get(period.game_id)
            payload = {
                'home_team_goals': game.home_team_goals,
                'home_team_fouls': period.home_team_fouls,
                'away_team_goals': game.away_team_goals,
                'away_team_fouls': period.away_team_fouls,
                'shootout': game.shootout.to_dict() if game.shootout else None,
            }
            hub_client = get_hub_client()
            if hub_client:
                hub_client.broadcast_to_class('game_data_receiver',
                                              'scoreboard_data', payload)
            from core.extensions import socketio as _sio
            _sio.emit('scoreboard_data', {'payload': payload})

    @socketio.on('broadcast_goal')
    def handle_broadcast_goal(data):
        from app.models.settings import Settings
        from app.models.game import Game

        settings  = Settings.get_settings()
        game      = Game.query.get(settings.current_game_id)
        team_type = data.get('team_type')
        team      = game.home_team if team_type == 'home' else game.away_team

        hub_client = get_hub_client()
        if hub_client:
            hub_client.send_to_plugin('stream-overlay', 'goal', team.to_dict())

    @socketio.on('add_game_event_to_db')
    def handle_add_game_event_to_db(data):
        from app.models.settings import Settings
        from app.models.game import Game

        settings  = Settings.get_settings()
        game_id   = settings.current_game_id
        period_id = settings.current_period_id

        if not game_id or not period_id:
            socketio.emit('error', {'message': 'Brak aktywnego meczu lub okresu'})
            return

        event_manager = GameEventManager()
        try:
            event_id = _resolve_event_id(data.get('event_type', ''))
        except ValueError as e:
            socketio.emit('error', {'message': str(e)})
            return

        # Odczyt aktualnego czasu z cache timera (in-memory), fallback na DB
        tm = get_timer_manager()
        period_mgr = PeriodManager()
        period = period_mgr.get_period_by_id(period_id)
        main_timer = tm.get_active_main_timer(period_id) if tm else None
        plugin_timer_id = main_timer.plugin_timer_id if main_timer else None
        timer_state = tm.get_timer_state(plugin_timer_id) if (tm and plugin_timer_id) else None

        if timer_state is not None:
            elapsed_ms = timer_state.get('elapsed_time', 0)
        elif main_timer is not None:
            elapsed_ms = main_timer.elapsed_time_ms
        else:
            elapsed_ms = 0

        initial_s = (period.initial_time // 1000) if period else 0
        game_time = (elapsed_ms // 1000) + initial_s

        game_event = event_manager.record_event(
            game_id=game_id,
            period_id=period_id,
            event_id=event_id,
            team_id=data.get('team_id'),
            player_id=data.get('player_id'),
            game_time=game_time,
        )
        if game_event:
            hub_client = get_hub_client()
            if hub_client:
                from app.models.settings import Settings as _S
                from core.managers.game_camera_manager import GameCameraManager
                _settings = _S.get_settings()
                cameras = (GameCameraManager().get_cameras_dict_for_game(_settings.current_game_id)
                           if _settings and _settings.current_game_id else
                           {'camera1': False, 'camera2': False, 'camera3': False, 'camera4': False})
                hub_client.broadcast(msg_type='recording_command', payload={
                    'requestType': 'GetRecordStatus',
                    'requestData': {},
                    'request_id': f'get-record-status-{game_event.id}',
                    'game_event_id': game_event.id,
                    'cameras': cameras,
                })
            socketio.emit('game_event_added', {'game_event': game_event.to_dict()})

    @socketio.on('update_game_event')
    def handle_update_game_event(data):
        gem = GameEventManager()
        success = gem.update_game_event(
            game_event_id=data.get('game_event_id'),
            team_id=data.get('team_id'),
            player_id=data.get('player_id'),
            home_team_goals=data.get('home_team_goals'),
            away_team_goals=data.get('away_team_goals'),
        )
        if success:
            socketio.emit('game_event_updated', {
                'game_event_id': success.id,
                'content_type':  data.get('content_type'),
            })

    @socketio.on('hide_game_event')
    def handle_hide_game_event(data):
        from app.models.game import Game
        from core.extensions import socketio as _sio

        gem = GameEventManager()
        game_event = gem.get_game_event_by_id(data.get('game_event_id'))
        if not game_event:
            return

        if game_event.event and game_event.event.filter_class == 'goal' and game_event.team_id:
            game = Game.query.get(game_event.game_id)
            if game:
                team = 'home' if game_event.team_id == game.home_team_id else 'away'
                period = PeriodManager().increment_period_goal(game_event.period_id, team, -1)
                if period:
                    game_now = Game.query.get(period.game_id)
                    payload = {
                        'home_team_goals': game_now.home_team_goals,
                        'home_team_fouls': period.home_team_fouls,
                        'away_team_goals': game_now.away_team_goals,
                        'away_team_fouls': period.away_team_fouls,
                    }
                    hc = get_hub_client()
                    if hc:
                        hc.broadcast_to_class('game_data_receiver', 'scoreboard_data', payload)
                    _sio.emit('scoreboard_data', {'payload': payload})

        success = gem.update_game_event(game_event_id=game_event.id, is_visible=False)
        if success:
            socketio.emit('game_event_hidden', {'game_event_id': success.id})

    @socketio.on('restore_game_event')
    def handle_restore_game_event(data):
        from app.models.game import Game
        from core.extensions import socketio as _sio

        gem = GameEventManager()
        game_event = gem.get_game_event_by_id(data.get('game_event_id'))
        if not game_event:
            return

        if game_event.event and game_event.event.filter_class == 'goal' and game_event.team_id:
            game = Game.query.get(game_event.game_id)
            if game:
                team = 'home' if game_event.team_id == game.home_team_id else 'away'
                period = PeriodManager().increment_period_goal(game_event.period_id, team, 1)
                if period:
                    game_now = Game.query.get(period.game_id)
                    payload = {
                        'home_team_goals': game_now.home_team_goals,
                        'home_team_fouls': period.home_team_fouls,
                        'away_team_goals': game_now.away_team_goals,
                        'away_team_fouls': period.away_team_fouls,
                    }
                    hc = get_hub_client()
                    if hc:
                        hc.broadcast_to_class('game_data_receiver', 'scoreboard_data', payload)
                    _sio.emit('scoreboard_data', {'payload': payload})

        success = gem.update_game_event(game_event_id=game_event.id, is_visible=True)
        if success:
            socketio.emit('game_event_restored', {'game_event_id': success.id})

    # =========================================================================
    # RECOVERY & QUERY
    # =========================================================================

    @socketio.on('timer_get_state')
    def handle_timer_get_state(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return
        timer_id = data.get('timer_id')
        state    = tm.get_timer_state(timer_id)
        if state:
            socketio.emit('timer_state', state)
        else:
            socketio.emit('error', {'message': f'Timer {timer_id} not found'})

    @socketio.on('timer_plugin_request_all_timers')
    def handle_timer_plugin_request_all_timers():
        tm = _get_timer_manager_or_error()
        if not tm:
            return
        if not tm.get_all_timers():
            socketio.emit('timer_plugin_offline', {'message': 'Timer plugin is not connected'})

    @socketio.on('timer_plugin_create_timer')
    def handle_timer_plugin_create_timer(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return

        timer_id   = data.get('timer_id')
        timer_type = data.get('timer_type', 'independent')
        keys       = ('parent_id', 'limit', 'pause_at_limit', 'initial_time', 'metadata')
        kwargs     = {k: data[k] for k in keys if k in data}

        if tm.create_timer(timer_id, timer_type, **kwargs):
            current_app.logger.info(f'Timer created: {timer_id}')
        else:
            socketio.emit('error', {'message': f'Failed to create timer {timer_id}'})

    @socketio.on('timer_plugin_start_timer')
    def handle_timer_plugin_start_timer(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return
        timer_id = data.get('timer_id')
        if not tm.start_timer(timer_id):
            socketio.emit('error', {'message': f'Failed to start timer {timer_id}'})
