"""SocketIO events"""
import datetime

from flask import current_app
from flask_socketio import emit

from app.extensions import socketio
from app.managers import get_hub_client, get_timer_manager, get_sequence_manager
from app.models.game_timer import GameTimer


# =============================================================================
# CONNECTION
# =============================================================================

@socketio.on('connect')
def handle_connect():
    current_app.logger.info('🔌 UI client connected')
    emit('connected', {'status': 'ok'})


@socketio.on('disconnect')
def handle_disconnect():
    current_app.logger.info('🔌 UI client disconnected')


# =============================================================================
# SHOOTOUT DATA
# =============================================================================
@socketio.on('get_shootouts')
def handle_get_shootout_data():
    from app.managers.shootout_manager import ShootoutManager
    from app.managers import get_shootout_kick_manager
    from app.models.settings import Settings
    settings = Settings.get_settings()
    current_game_id = settings.current_game_id
    shootout_manager = ShootoutManager()
    shootout = shootout_manager.get_shootout_by_game(current_game_id).to_dict()
    sh_kick_manager = get_shootout_kick_manager()
    kicks = sh_kick_manager.get_kicks_by_game(current_game_id)
    emit('response_get_shootouts', {'shootout': shootout, 'kicks': kicks})

@socketio.on('get_game_teams')
def handle_get_game_teams():
    from app.managers.game_player_manager import GamePlayerManager
    from app.managers.game_player_manager import GamePlayer
    from app.managers.game_manager import GameManager
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


    emit('response_get_game_teams', {
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

    settings   = Settings.get_settings()
    period     = Period.query.get(settings.current_period_id)
    game       = Game.query.get(period.game_id).to_dict()
    is_reversed = bool(settings.is_scoreboard_reversed)

    timer_manager = get_timer_manager()
    main_gt = (
        timer_manager.get_active_main_timer(settings.current_period_id)
        if timer_manager else None
    )
    penalties = (
        timer_manager._get_penalties_dict(settings.current_period_id)
        if timer_manager else {'home': [], 'away': []}
    )

    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast_to_class('overlay', 'game_data', game)

    emit('initial_data', {
        'home_team_goals':  game['home_team_goals'],
        'away_team_goals':  game['away_team_goals'],
        'home_team_fouls':  game['home_team_fouls'],
        'away_team_fouls':  game['away_team_fouls'],
        'home_penalties':   penalties['home'],
        'away_penalties':   penalties['away'],
        'main_timer':       main_gt.to_dict() if main_gt else None,
        'is_reversed':      is_reversed,
    })


@socketio.on('reverse_scoreboard')
def handle_reverse_scoreboard(data):
    from app.models.settings import Settings
    Settings.set_scoreboard_order(data.get('is_scoreboard_reversed'))


# =============================================================================
# OVERLAY
# =============================================================================

@socketio.on('show_overlay_container')
def handle_show_overlay_container(_data):
    from app.utils.socketio_events_utils import generate_show_overlay_data
    data = generate_show_overlay_data(_data)
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast_to_class('overlay', 'show_overlay_container',
                                      payload=data)



# =============================================================================
# RECORDING
# =============================================================================

@socketio.on('start_recording')
def handle_start_recording():
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast(msg_type='recording_command', payload={
            'requestType': 'StartRecord',
            'requestData': {},
            'request_id': f'rec-start-{datetime.datetime.now()}',
            'cameras': {'camera1': True, 'camera2': False,
                        'camera3': False, 'camera4': False},
        })


@socketio.on('stop_recording')
def handle_stop_recording():
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast(msg_type='recording_command', payload={
            'requestType': 'StopRecord',
            'requestData': {},
            'request_id': f'rec-stop-{datetime.datetime.now()}',
            'cameras': {'camera1': True, 'camera2': False,
                        'camera3': False, 'camera4': False},
        })


@socketio.on('get_obs_ws_connection')
def handle_get_obs_ws_connection():
    hub_client = get_hub_client()
    if hub_client:
        hub_client.send_to_plugin('obs-ws-plugin', 'obs_command', {
            'requestType': 'GetVersion',
            'request_id': 'get-websocket-connection',
            'requestData': {},
        })


# =============================================================================
# BASIC TIMER CONTROL
# =============================================================================

def _get_timer_manager_or_error():
    tm = get_timer_manager()
    if not tm:
        emit('error', {'message': 'Timer manager not available'})
    return tm


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
        emit('error', {'message': f'Failed to create timer {timer_id}'})


@socketio.on('timer_start')
def handle_timer_start(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return

    timer_id = data.get('timer_id')
    if not tm.start_timer(timer_id):
        emit('error', {'message': f'Failed to start timer {timer_id}'})
        return

    # Aktualizacja DB przez ORM
    from app.models.settings import Settings
    period_id = Settings.get_settings().current_period_id

    main_gt = tm.get_active_main_timer(period_id)
    if main_gt and main_gt.plugin_timer_id == timer_id:
        # Główny timer ruszył — startuj wszystkie aktywne kary
        for pen in tm.get_active_penalties(period_id):
            if pen.plugin_timer_id:
                tm.start_timer(pen.plugin_timer_id)
            pen.state = GameTimer.STATE_RUNNING
        from app.extensions import db
        db.session.commit()
    else:
        # Pojedyncza kara
        gt = tm.get_db_timer(timer_id)
        if gt:
            gt.state = GameTimer.STATE_RUNNING
            from app.extensions import db
            db.session.commit()


@socketio.on('timer_pause')
def handle_timer_pause(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return

    timer_id = data.get('timer_id')
    tm.pause_timer(timer_id)

    from app.models.settings import Settings
    from app.extensions import db
    period_id = Settings.get_settings().current_period_id
    main_gt = tm.get_active_main_timer(period_id)

    if main_gt and main_gt.plugin_timer_id == timer_id:
        # Główny timer zapauzowany — pauzuj wszystkie kary
        for pen in tm.get_active_penalties(period_id):
            if pen.plugin_timer_id:
                tm.pause_timer(pen.plugin_timer_id)
            pen.state = GameTimer.STATE_PAUSED
        db.session.commit()
    else:
        gt = tm.get_db_timer(timer_id)
        if gt:
            gt.state = GameTimer.STATE_PAUSED
            db.session.commit()


@socketio.on('timer_resume')
def handle_timer_resume(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return

    timer_id = data.get('timer_id')
    if not tm.resume_timer(timer_id):
        emit('error', {'message': f'Failed to resume timer {timer_id}'})
        return

    from app.models.settings import Settings
    from app.extensions import db
    period_id = Settings.get_settings().current_period_id
    main_gt = tm.get_active_main_timer(period_id)

    if main_gt and main_gt.plugin_timer_id == timer_id:
        # Wznów kary które były paused (nie te co dobiegły limitu)
        for pen in tm.get_active_penalties(period_id):
            if pen.state == GameTimer.STATE_PAUSED and pen.plugin_timer_id:
                tm.resume_timer(pen.plugin_timer_id)
                pen.state = GameTimer.STATE_RUNNING
        db.session.commit()
    else:
        gt = tm.get_db_timer(timer_id)
        if gt:
            gt.state = GameTimer.STATE_RUNNING
            db.session.commit()

    emit('timer_resumed', {'timer_id': timer_id}, broadcast=True)


@socketio.on('timer_reset')
def handle_timer_reset(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return
    timer_id = data.get('timer_id')
    if not tm.reset_timer(timer_id):
        emit('error', {'message': f'Failed to reset timer {timer_id}'})


@socketio.on('timer_remove')
def handle_timer_remove(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return

    from app.extensions import db
    timer_id = data.get('timer_id')
    current_app.logger.info(f'🗑️  Attempting to remove timer: {timer_id}')

    # Nie pozwól usunąć głównego timera
    gt = tm.get_db_timer(timer_id)
    if gt is None or gt.timer_type == GameTimer.TYPE_MAIN:
        emit('error', {'message': 'Cannot remove main timer or timer not found'})
        return

    game_id = gt.game_id

    if tm.remove_timer(timer_id):
        gt.state = GameTimer.STATE_REMOVED
        db.session.commit()

        penalties = tm._get_penalties_dict(game_id)
        emit('reload_penalty_timers', {'penalties': penalties}, broadcast=True)
        tm._broadcast_penalty_state(game_id)
    else:
        emit('error', {'message': f'Failed to remove timer {timer_id}'})


# =============================================================================
# TIME SYNCHRONIZATION
# =============================================================================

@socketio.on('timer_adjust')
def handle_timer_adjust(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return

    timer_id = data.get('timer_id')
    delta    = data.get('delta', 0)

    if tm.adjust_time(timer_id, delta):
        # Dla kar — zapisz korektę jako adjustment_ms w DB
        gt = tm.get_db_timer(timer_id)
        if gt and gt.timer_type == GameTimer.TYPE_PENALTY:
            gt.apply_adjustment(delta)
            from app.extensions import db
            db.session.commit()

        emit('timer_adjusted', {'timer_id': timer_id, 'delta': delta},
             broadcast=True)
    else:
        emit('error', {'message': f'Failed to adjust timer {timer_id}'})


@socketio.on('timer_set_time')
def handle_timer_set_time(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return

    timer_id     = data.get('timer_id')
    elapsed_time = data.get('elapsed_time', 0)

    if tm.set_elapsed_time(timer_id, elapsed_time):
        emit('timer_time_set', {'timer_id': timer_id, 'elapsed_time': elapsed_time},
             broadcast=True)
    else:
        emit('error', {'message': f'Failed to set time for timer {timer_id}'})


# =============================================================================
# HIGH-LEVEL MATCH OPERATIONS
# =============================================================================

@socketio.on('match_timer_create')
def handle_game_timer_create(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return

    game_id          = data.get('game_id')
    duration_minutes = data.get('duration_minutes', 40)
    timer_id         = tm.create_game_timer(game_id, duration_minutes)

    emit('match_timer_created', {'game_id': game_id, 'timer_id': timer_id},
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
        emit('error', {'message': f'Max 2 active penalties per team'})
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
            'home_team_fouls': game.home_team_fouls,
            'away_team_goals': game.away_team_goals,
            'away_team_fouls': game.away_team_fouls,
        }
        hub_client = get_hub_client()
        if hub_client:
            hub_client.broadcast_to_class('game_data_receiver',
                                          'scoreboard_data', payload)
        emit('scoreboard_data', {'payload': payload})


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
    from app.managers.game_event_manager import GameEventManager

    settings  = Settings.get_settings()
    game_id   = settings.current_game_id
    period_id = settings.current_period_id

    if not game_id or not period_id:
        emit('error', {'message': 'Brak aktywnego meczu lub okresu'})
        return

    # Czas zdarzenia — z DB timera lub cache
    tm = get_timer_manager()
    main_gt = tm.get_active_main_timer(period_id) if tm else None
    elapsed_ms = main_gt.elapsed_time_ms if main_gt else 0

    period_manager = PeriodManager()
    period_data    = period_manager.get_period_by_id(period_id).to_dict()
    initial_s      = int(period_data['initial_time_seconds'])
    elapsed_s      = elapsed_ms // 1000
    game_time      = elapsed_s + initial_s

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
        emit('error', {'message': str(e)})
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
    from app.managers.game_event_manager import GameEventManager
    from app.managers.game_player_manager import GamePlayerManager

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
        })


# =============================================================================
# UI MONITOR
# =============================================================================

@socketio.on('request_ui_monitor_content')
def handle_request_ui_monitor_content(data):
    content_type = data.get('type')

    if content_type is None:
        emit('show_ui_monitor_content', {'content_type': None})
        return

    if content_type == 'events':
        from app.managers.event_manager import EventManager
        from app.managers.game_event_manager import GameEventManager
        from app.models.settings import Settings
        from app.managers.game_manager import GameManager

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

        emit('show_ui_monitor_content', {
            'content_type': 'events',
            'events_types': events_types,
            'game_events':  game_events,
        })

    elif content_type == 'edit_event':
        from app.managers.event_manager import EventManager
        from app.models.settings import Settings

        payload      = data.get('payload', {})
        game_event_d = _get_game_event_data(payload['game_event_id'])
        events_types = [
            e.to_dict() for e in EventManager().get_all_events()
            if e.filter_class
        ]
        emit('show_ui_monitor_content', {
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
        emit('show_ui_monitor_content', {
            'content_type': 'get_event_squad',
            'game_event':   game_event_d['game_event'],
            'team_squad':   game_event_d['team_squad'],
        })


def _get_game_event_data(game_event_id, new_event_type_id=None):
    from app.managers.game_event_manager import GameEventManager
    from app.managers.game_manager import GameManager

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
    from app.managers.game_event_manager import GameEventManager

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
        emit('game_event_updated', {
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
        emit('timer_state', state)
    else:
        emit('error', {'message': f'Timer {timer_id} not found'})


@socketio.on('timers_get_all')
def handle_timers_get_all():
    tm = _get_timer_manager_or_error()
    if tm:
        tm.get_all_timers()


@socketio.on('timer_plugin_request_all_timers')
def handle_timer_plugin_request_all_timers():
    current_app.logger.info('📥 UI requested all timers from plugin')
    tm = _get_timer_manager_or_error()
    if not tm:
        return
    if not tm.get_all_timers():
        emit('timer_plugin_offline', {'message': 'Timer plugin is not connected'})


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
        emit('error', {'message': f'Failed to create timer {timer_id}'})


@socketio.on('timer_plugin_start_timer')
def handle_timer_plugin_start_timer(data):
    current_app.logger.info(f'📥 UI requested timer start: {data.get("timer_id")}')
    tm = _get_timer_manager_or_error()
    if not tm:
        return
    timer_id = data.get('timer_id')
    if not tm.start_timer(timer_id):
        emit('error', {'message': f'Failed to start timer {timer_id}'})


# =============================================================================
# SEQUENCES
# =============================================================================

@socketio.on('trigger_sequence')
def handle_trigger_sequence(data):
    sm          = get_sequence_manager()
    sequence_id = sm.trigger(data['sequence'], data.get('context', {}))
    emit('sequence_started', {'sequence_id': sequence_id})


@socketio.on('stop_sequence')
def handle_stop_sequence(data):
    sm          = get_sequence_manager()
    sequence_id = data.get('sequence_id')
    if sequence_id:
        sm.stop(sequence_id)
        emit('sequence_stopped', {'sequence_id': sequence_id})
    else:
        sm.stop_all(data.get('sequence'))
        emit('all_sequences_stopped', {})


# =============================================================================
# RAFTING / SKIING
# =============================================================================

@socketio.on('rafting_timer_create')
def handle_rafting_timer_create(data):
    tm = _get_timer_manager_or_error()
    if not tm:
        return
    team_name    = data.get('team_name')
    start_number = data.get('start_number')
    timer_id     = tm.create_rafting_timer(team_name, start_number)
    emit('rafting_timer_created', {
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
    emit('skiing_timers_created', {
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
        emit('skiing_started', {
            'blue_timer_id': blue_id, 'red_timer_id': red_id,
        }, broadcast=True)
    else:
        emit('error', {'message': 'Failed to start skiing timers'})


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _resolve_event_id(event_type: str) -> int:
    from app.models.event import Event
    event = Event.query.filter(Event.name.ilike(event_type)).first()
    if not event:
        raise ValueError(f"Nieznany typ zdarzenia: '{event_type}'")
    return event.id
