"""
app.socketio_events.futsal — handlery SocketIO specyficzne dla futsal-nalf.

Rejestracja: futsal_events.register_events(socketio)
"""
import logging
from flask import current_app
from core.managers import (get_hub_client, get_timer_manager,
                           get_sequence_manager, get_recorder_manager)
from core.managers.game_event_manager import GameEventManager
from core.managers.game_manager import GameManager

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
    """Rejestruje handlery SocketIO specyficzne dla futsal-nalf."""

    @socketio.on('get_shootouts')
    def handle_get_shootout_data():
        from app.models.shootout import Shootout
        from core.managers.shootout_kick_manager import ShootoutKickManager
        from app.models.settings import Settings
        settings = Settings.get_settings()
        current_game_id = settings.current_game_id
        current_shootout_id = settings.current_shootout_id
        if current_shootout_id:
            shootout = Shootout.query.get(current_shootout_id).to_dict()
            sh_kick_manager = ShootoutKickManager()
            kicks = sh_kick_manager.get_kicks_by_game(current_game_id)
            socketio.emit('response_get_shootouts', {'shootout': shootout, 'kicks': kicks})

    @socketio.on('get_game_teams')
    def handle_get_game_teams():
        # from core.managers.game_player_manager import GamePlayerManager
        from app.managers.game_player_manager import GamePlayerManager
        from app.models.game_player import GamePlayer
        from core.managers.game_manager import GameManager
        from app.models.settings import Settings
        import json
        settings = Settings.get_settings()
        current_game_id = settings.current_game_id
        game_manager = GameManager()
        game = game_manager.get_game_by_id(game_id=current_game_id)
        print('game:', game.to_dict())
        game_data = game.to_dict()
        game_player_manager = GamePlayerManager()
        game_player = GamePlayer()
        home_team_id = game_data['home_team_id']
        away_team_id = game_data['away_team_id']
        home_players = [gp.to_squad_dict() for gp in game_player_manager.get_players_for_game(game_id=game.id, team_id=home_team_id)]
        away_players = [gp.to_squad_dict() for gp in game_player_manager.get_players_for_game(game_id=game.id, team_id=away_team_id)]


        socketio.emit('response_get_game_teams', {
            'game_data': game_data,
            'home_team_players': home_players,
            'away_team_players': away_players,
        })

    # =============================================================================
    # INITIAL DATA
    # =============================================================================

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
        else:
            from app.models.shootout import Shootout
            game_obj = Game.query.get(settings.current_game_id) if settings.current_game_id else None
            game = game_obj.to_dict() if game_obj else None

            shootout_obj = Shootout.query.get(settings.current_shootout_id) if settings.current_shootout_id else None
            _data = {
                'home_team_short_name': game['home_team_short_name'],
                'away_team_short_name': game['away_team_short_name'],
            }
            if shootout_obj:
                shootout = shootout_obj.to_dict() if shootout_obj else None
                _data.update({
                    'home_team_shootouts': shootout['home_team_shootouts'],
                    'away_team_shootouts': shootout['away_team_shootouts'],
                    'score_string': shootout['score_string']
                })

            socketio.emit('shootout_initial_data', _data)

    @socketio.on('add_team_event')
    def handle_add_team_event(data):
        team_type = data.get('team_type')
        event_name = data.get('event_name')
        socketio.emit('team_event_added', {'team_type': team_type, 'event_name': event_name})


    # =============================================================================
    # OVERLAY
    # =============================================================================

    @socketio.on('get_record_status')
    def handle_get_record_status():
        hub_client = get_hub_client()
        if hub_client:
            from datetime import datetime
            hub_client.broadcast(msg_type='recording_command', payload={
                'requestType': 'GetRecordStatus',
                'requestData': {},
                'request_id': f'rec-status-{datetime.now()}',
                'cameras': {'camera1': True, 'camera2': False,
                            'camera3': False, 'camera4': False},
            })

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
        duration_minutes = data.get('duration_minutes', 40)
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

        # Max 2 aktywne kary na drużynę
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


    # =============================================================================
    # GAME SCORE / EVENTS
    # =============================================================================

    @socketio.on('change_game_value')
    def handle_change_game_value(data):
        from app.models.settings import Settings
        from app.models.game import Game
        from app.managers.period_manager import PeriodManager

        period_manager   = PeriodManager()
        current_game_id  = Settings.get_settings().current_game_id
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

        settings     = Settings.get_settings()
        game         = Game.query.get(settings.current_game_id)
        team_type    = data.get('team_type')
        team         = game.home_team if team_type == 'home' else game.away_team

        hub_client = get_hub_client()
        if hub_client:
            hub_client.send_to_plugin('stream-overlay', 'goal', team.to_dict())

    @socketio.on('add_game_event_to_db')
    def handle_add_game_event_to_db(data):
        from app.models.settings import Settings
        from app.models.game import Game
        from app.managers.period_manager import PeriodManager
        from core.managers.game_event_manager import GameEventManager

        settings  = Settings.get_settings()
        game_id   = settings.current_game_id
        period_id = settings.current_period_id

        if not game_id or not period_id:
            socketio.emit('error', {'message': 'Brak aktywnego meczu lub okresu'})
            return

        # Czas zdarzenia — z in-memory cache timera (aktualny elapsed_ms),
        # z fallbackiem na DB (ostatni zsynchronizowany stan).
        # WAŻNE: cache jest indeksowany przez plugin_timer_id (np. "main-p2"),
        # nie przez DB id — stąd używamy main_timer.plugin_timer_id jako klucza.
        tm = get_timer_manager()
        main_timer    = tm.get_active_main_timer(period_id)
        plugin_timer_id = main_timer.plugin_timer_id if main_timer else None
        timer_state   = tm.get_timer_state(plugin_timer_id) if plugin_timer_id else None

        if timer_state is not None:
            # Cache aktualny — używaj go (najbardziej aktualny elapsed_ms z ticków)
            elapsed_ms = timer_state.get('elapsed_time', 0)
        elif main_timer is not None:
            # Cache zimny (np. po restarcie serwera) — fallback na DB
            elapsed_ms = main_timer.elapsed_time_ms
        else:
            elapsed_ms = 0

        period_manager = PeriodManager()
        period         = period_manager.get_period_by_id(period_id)
        # game_time zapisujemy w sekundach (spójnie z game_time_formatted i _build_goal_entry)
        # initial_time okresu to suma limitów poprzednich części w ms → dzielimy przez 1000
        initial_s = period.initial_time // 1000
        elapsed_s = elapsed_ms // 1000
        game_time = elapsed_s + initial_s

        # Drużyna
        team_id   = None
        team_type = data.get('team_type')
        if team_type in ('home', 'away'):
            game    = Game.query.get(game_id)
            team_id = game.home_team_id if team_type == 'home' else game.away_team_id

        try:
            manager    = GameEventManager()
            game_event = manager.record_event(
                game_id=game_id,
                event_id=_resolve_event_id(data.get('event_type')),
                period_id=period_id,
                team_id=team_id,
                event_place=data.get('selected_cell_id'),
                game_time=game_time,
            )
        except Exception as e:
            current_app.logger.error(f'❌ Failed to save game event: {e}')
            socketio.emit('error', {'message': str(e)})
            return

        hub_client = get_hub_client()
        if hub_client:
            hub_client.broadcast(msg_type='recording_command', payload={
                'requestType': 'GetRecordStatus',
                'requestData': {},
                'request_id': f'get-record-status-{game_event.id}',
                'game_event_id': game_event.id,
                'cameras': {'camera1': True, 'camera2': False,
                            'camera3': False, 'camera4': False},
            })

    @socketio.on('show_info')
    def handle_show_info(data):
        from core.managers.game_event_manager import GameEventManager
        from core.managers.game_player_manager import GamePlayerManager

        gm  = GameEventManager()
        gpm = GamePlayerManager()

        game_event  = gm.get_game_event_by_id(data.get('game_event_id'))
        ged         = game_event.to_dict()
        game_player = gpm.get_game_player_by_player_id(ged['player_id'])
        gpd         = game_player.to_dict()

        hub_client = get_hub_client()
        if hub_client:
            hub_client.send_to_plugin('stream-overlay', 'show_info', {
                'event_type_id':       ged['event_id'],
                'event_name':          ged['event_name'],
                'event_image_path':    ged['event_image_path'],
                'team_name':           ged['team_name'],
                'team_name_14':        ged['team_name_14'],
                'player_number':       ged['player_number'],
                'player_name':         ged['player_name'],
                'player_team_short_name': gpd['team_short_name'],
                'game_time':           ged['game_time'],
                'period_limit_s':   (game_event.period.initial_time + game_event.period.limit) // 1000,
            })


    # =============================================================================
    # UI MONITOR
    # =============================================================================

    @socketio.on('request_ui_monitor_content')
    def handle_request_ui_monitor_content(data):
        content_type = data.get('type')

        if content_type is None:
            socketio.emit('show_ui_monitor_content', {'content_type': None})
            return

        if content_type == 'events':
            from core.managers.event_manager import EventManager
            from core.managers.game_event_manager import GameEventManager
            from app.models.settings import Settings
            from core.managers.game_manager import GameManager

            settings   = Settings.get_settings()
            game       = GameManager().get_game_by_id(settings.current_game_id)
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

            socketio.emit('show_ui_monitor_content', {
                'content_type': 'events',
                'events_types': events_types,
                'game_events':  game_events,
            })

        elif content_type == 'edit_event':
            from core.managers.event_manager import EventManager
            from app.models.settings import Settings

            payload      = data.get('payload', {})
            game_event_d = _get_game_event_data(payload['game_event_id'])
            events_types = [
                e.to_dict() for e in EventManager().get_all_events()
                if e.filter_class
            ]
            socketio.emit('show_ui_monitor_content', {
                'content_type':          'edit_event',
                'events_types':          events_types,
                'is_scoreboard_reversed': bool(Settings.get_settings().is_scoreboard_reversed),
                'team_squad':            game_event_d['team_squad'],
                'game_event':            game_event_d['game_event'],
            })

        elif content_type == 'get_event_squad':
            payload      = data.get('payload', {})
            game_event_d = _get_game_event_data(
                payload['game_event_id'], payload.get('new_event_type_id')
            )
            socketio.emit('show_ui_monitor_content', {
                'content_type': 'get_event_squad',
                'game_event':   game_event_d['game_event'],
                'team_squad':   game_event_d['team_squad'],
            })


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

    @socketio.on('update_game_event')
    def handle_update_game_event(data):
        from core.managers.game_event_manager import GameEventManager

        gem     = GameEventManager()
        success = gem.update_game_event(
            game_event_id=data.get('game_event_id'),
            event_id=data.get('event_id'),
            game_time=data.get('game_time'),
            replay_end_time=data.get('replay_end_time'),
            replay_start_time=data.get('replay_start_time'),
            video_path=data.get('video_path'),
            event_place=data.get('event_place'),
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


    # =============================================================================
    # RECOVERY & QUERY
    # =============================================================================

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
        current_app.logger.info('📥 UI requested all timers from plugin')
        tm = _get_timer_manager_or_error()
        if not tm:
            return
        if not tm.get_all_timers():
            socketio.emit('timer_plugin_offline', {'message': 'Timer plugin is not connected'})

    @socketio.on('timer_plugin_create_timer')
    def handle_timer_plugin_create_timer(data):
        current_app.logger.info(f'📥 UI requested timer creation: {data.get("timer_id")}')
        tm = _get_timer_manager_or_error()
        if not tm:
            return

        timer_id   = data.get('timer_id')
        timer_type = data.get('timer_type', 'independent')
        keys       = ('parent_id', 'limit', 'pause_at_limit', 'initial_time', 'metadata')
        kwargs     = {k: data[k] for k in keys if k in data}

        if tm.create_timer(timer_id, timer_type, **kwargs):
            current_app.logger.info(f'✅ Timer created: {timer_id}')
        else:
            socketio.emit('error', {'message': f'Failed to create timer {timer_id}'})

    @socketio.on('timer_plugin_start_timer')
    def handle_timer_plugin_start_timer(data):
        current_app.logger.info(f'📥 UI requested timer start: {data.get("timer_id")}')
        tm = _get_timer_manager_or_error()
        if not tm:
            return
        timer_id = data.get('timer_id')
        if not tm.start_timer(timer_id):
            socketio.emit('error', {'message': f'Failed to start timer {timer_id}'})


    # =============================================================================
    # SEQUENCES
    # =============================================================================

    @socketio.on('rafting_timer_create')
    def handle_rafting_timer_create(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return
        team_name    = data.get('team_name')
        start_number = data.get('start_number')
        timer_id     = tm.create_rafting_timer(team_name, start_number)
        socketio.emit('rafting_timer_created', {
            'timer_id': timer_id, 'team_name': team_name,
            'start_number': start_number,
        }, broadcast=True)

    @socketio.on('skiing_timers_create')
    def handle_skiing_timers_create(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return
        blue_id, red_id = tm.create_parallel_skiing_timers(
            data.get('skier_blue', {}), data.get('skier_red', {})
        )
        socketio.emit('skiing_timers_created', {
            'blue_timer_id': blue_id, 'red_timer_id': red_id,
        }, broadcast=True)

    @socketio.on('skiing_start_simultaneous')
    def handle_skiing_start_simultaneous(data):
        tm = _get_timer_manager_or_error()
        if not tm:
            return
        blue_id = data.get('blue_timer_id')
        red_id  = data.get('red_timer_id')
        if tm.start_multiple([blue_id, red_id]):
            socketio.emit('skiing_started', {
                'blue_timer_id': blue_id, 'red_timer_id': red_id,
            }, broadcast=True)
        else:
            socketio.emit('error', {'message': 'Failed to start skiing timers'})


    # =============================================================================
    # INTERNAL HELPERS
    # =============================================================================

    def _resolve_event_id(event_type: str) -> int:
        from app.models.event import Event
        event = Event.query.filter(Event.name.ilike(event_type)).first()
        if not event:
            raise ValueError(f"Nieznany typ zdarzenia: '{event_type}'")
        return event.id


    # =============================================================================
    # REPLAY EXPORT
    # =============================================================================

    # socketio_events.py