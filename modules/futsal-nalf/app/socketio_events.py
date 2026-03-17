"""SocketIO events - MINIMAL"""
from flask import current_app, jsonify
from flask_socketio import emit
from app.extensions import socketio
from app.managers import get_hub_client
from app.managers import get_timer_manager
from app.managers import get_sequence_manager
import json
import datetime

@socketio.on('connect')
def handle_connect():
    current_app.logger.info('🔌 UI client connected')
    emit('connected', {'status': 'ok'})

@socketio.on('request_initial_data')
def handle_request_initial_data():
    from app.models.settings import Settings
    from app.models.period import Period
    from app.models.game import Game
    from app.models.team import Team

    settings = Settings.get_settings()
    current_period_id = settings.current_period_id
    current_period = Period.query.get(current_period_id)
    current_timers = Settings.get_current_timers()
    home_penalties = current_timers['penalties']['home']
    away_penalties = current_timers['penalties']['away']
    # penalties = {'home': home_penalties, 'away': away_penalties}
    main_timer = current_timers['main']
    is_reversed = bool(settings.is_scoreboard_reversed)
    current_game = Game.query.get(current_period.game_id).to_dict()
    # home_team_id = current_game.home_team_id
    # home_team = current_game['home_team']
    # away_team_id = current_game.away_team_id
    # away_team = current_game['away_team']

    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast_to_class('overlay', 'game_data', current_game)

    emit('initial_data', {
        'home_team_goals': current_game['home_team_goals'],
        'away_team_goals': current_game['away_team_goals'],
        'home_team_fouls': current_game['home_team_fouls'],
        'away_team_fouls': current_game['away_team_fouls'],
        'home_penalties': home_penalties,
        'away_penalties': away_penalties,
        # 'teams': {'home': home_team, 'away': away_team},
        'main_timer': main_timer,
        'is_reversed': is_reversed
        })


@socketio.on('reverse_scoreboard')
def handle_reverse_scoreboard(data):
    from app.models.settings import Settings
    is_reversed = data.get('is_scoreboard_reversed')
    print('is_reversed', is_reversed)
    Settings.set_scoreboard_order(is_reversed)


@socketio.on('disconnect')
def handle_disconnect():
    current_app.logger.info('🔌 UI client disconnected')

@socketio.on('show_overlay_container')
def handle_show_overlay_container(data):
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast_to_class('overlay', 'show_overlay_container', payload=data)

@socketio.on('start_recording')
def handle_start_recording():
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast(msg_type='recording_command', payload={
        # hub_client.broadcast_to_class(class_name='recorder_device', msg_type='recording_command', payload={
            'requestType': 'StartRecord',
            'requestData': {},
            'request_id': f'my-unique-id-{datetime.datetime.now()}',
            'cameras':{'camera1': True,
                       'camera2': False,
                       'camera3': False,
                       'camera4': False}})
        

@socketio.on('stop_recording')
def handle_stop_recording():
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast(msg_type='recording_command', payload={
        # hub_client.broadcast_to_class(class_name='recorder_device', msg_type='recording_command', payload={
            'requestType': 'StopRecord',
            'request_id': f'my-unique-id-{datetime.datetime.now()}',
            'requestData': {},
            'cameras':{'camera1': True,
                       'camera2': False,
                       'camera3': False,
                       'camera4': False}})
        
@socketio.on('get_obs_ws_connection')
def handle_get_obs_ws_connection():
    hub_client = get_hub_client()
    if hub_client:
        hub_client.send_to_plugin(plugin_id='obs-ws-plugin', msg_type='obs_command', payload={
            'requestType': 'GetVersion',
            'request_id': 'get-websocket-connection',
            'requestData': {},
            })

@socketio.on('goal_scored')
def handle_goal_scored(data):
    team = data.get('team')
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast('goal_scored', {'team': team})
        emit('match_updated', {'team': team}, broadcast=True)
        
# ============================================================================
# BASIC TIMER CONTROL
# ============================================================================

@socketio.on('timer_create')
def handle_timer_create(data):
    """
    Create a new timer
    
    Client sends:
    {
        'timer_id': 'match-123',
        'timer_type': 'independent',
        'limit': 2400000,
        'update_interval_ms': 100,
        'metadata': {'sport': 'futsal'}
    }
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    timer_type = data.get('timer_type', 'independent')
    
    # Extract optional parameters
    kwargs = {}
    if 'parent_id' in data:
        kwargs['parent_id'] = data['parent_id']
    if 'limit' in data:
        kwargs['limit'] = data['limit']
    if 'pause_at_limit' in data:
        kwargs['pause_at_limit'] = data['pause_at_limit']
    if 'initial_time' in data:
        kwargs['initial_time'] = data['initial_time']
    if 'update_interval_ms' in data:
        kwargs['update_interval_ms'] = data['update_interval_ms']
    if 'metadata' in data:
        kwargs['metadata'] = data['metadata']
    
    success = timer_manager.create_timer(timer_id, timer_type, **kwargs)

    if not success:
        emit('error', {'message': f'Failed to create timer {timer_id}'})


@socketio.on('timer_start')
def handle_timer_start(data):
    """
    Start a timer
    
    Client sends: {'timer_id': 'match-123'}
    """
    from app.models.settings import Settings
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    success = timer_manager.start_timer(timer_id)
    
    if success:
        # Update state in Settings
        current_timers = Settings.get_current_timers()
        main_timer = current_timers.get("main")
        
        if main_timer and main_timer.get("timer_id") == timer_id:
            # Main timer started - also start all dependent penalties
            main_timer["state"] = "running"
            Settings.update_main_timer(main_timer)
            
            # Start all penalty timers (dependent)
            _penalties = current_timers.get("penalties", {"home": [], "away": []})
            penalties = _penalties['home'] + _penalties['away']
            for penalty in penalties:
                penalty_id = penalty.get("timer_id")
                if penalty_id:
                    # Start penalty timer
                    timer_manager.start_timer(penalty_id)
                    penalty["state"] = "running"
                    Settings.update_penalty_timer(penalty_id, penalty)
        else:
            # Penalty timer started
            _penalties = current_timers.get("penalties", {"home": [], "away": []})
            penalties = _penalties['home'] + _penalties['away']
            for penalty in penalties:
                if penalty.get("timer_id") == timer_id:
                    penalty["state"] = "running"
                    Settings.update_penalty_timer(timer_id, penalty)
                    break
        
    #     emit('timer_started', {'timer_id': timer_id}, broadcast=True)
    # else:
    #     emit('error', {'message': f'Failed to start timer {timer_id}'})


@socketio.on('timer_pause')
def handle_timer_pause(data):
    """
    Pause a timer
    
    Client sends: {'timer_id': 'match-123'}
    """
    from app.models.settings import Settings
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    timer_manager.pause_timer(timer_id)
    
    # Update state in Settings
    current_timers = Settings.get_current_timers()
    main_timer = current_timers.get("main")
    
    if main_timer and main_timer.get("timer_id") == timer_id:
        # Main timer paused - also pause all dependent penalties
        timer_state = timer_manager.get_timer_state(timer_id)
        if timer_state:
            main_timer["state"] = "paused"
            main_timer["elapsed_time"] = timer_state.get("elapsed_time", main_timer.get("elapsed_time", 0))
            Settings.update_main_timer(main_timer)
            
            # Pause all penalty timers (dependent)
            _penalties = current_timers.get("penalties", {"home": [], "away": []})
            penalties = _penalties['home'] + _penalties['away']
            for penalty in penalties:
                penalty_id = penalty.get("timer_id")
                if penalty_id:
                    # Pause penalty timer
                    timer_manager.pause_timer(penalty_id)
                    penalty_state = timer_manager.get_timer_state(penalty_id)
                    if penalty_state:
                        penalty["state"] = "paused"
                        penalty["elapsed_time"] = penalty_state.get("elapsed_time", penalty.get("elapsed_time", 0))
                        Settings.update_penalty_timer(penalty_id, penalty)
    else:
        # Penalty timer paused
        _penalties = current_timers.get("penalties", {"home": [], "away": []})
        penalties = _penalties['home'] + _penalties['away']
        for penalty in penalties:
            if penalty.get("timer_id") == timer_id:
                timer_state = timer_manager.get_timer_state(timer_id)
                if timer_state:
                    penalty["state"] = "paused"
                    penalty["elapsed_time"] = timer_state.get("elapsed_time", penalty.get("elapsed_time", 0))
                    Settings.update_penalty_timer(timer_id, penalty)
                break
    
    # if success:
    #     emit('timer_paused', {'timer_id': timer_id}, broadcast=True)
    # else:
    #     emit('error', {'message': f'Failed to pause timer {timer_id}'})


@socketio.on('timer_resume')
def handle_timer_resume(data):
    """
    Resume a paused timer
    
    Client sends: {'timer_id': 'match-123'}
    """
    from app.models.settings import Settings
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    success = timer_manager.resume_timer(timer_id)
    
    if success:
        # Update state in Settings
        current_timers = Settings.get_current_timers()
        main_timer = current_timers.get("main")
        
        if main_timer and main_timer.get("timer_id") == timer_id:
            # Main timer resumed - also resume all dependent penalties
            main_timer["state"] = "running"
            Settings.update_main_timer(main_timer)
            
            # Resume all penalty timers (dependent)
            _penalties = current_timers.get("penalties", {"home": [], "away": []})
            penalties = _penalties['home'] + _penalties['away']
            for penalty in penalties:
                penalty_id = penalty.get("timer_id")
                if penalty_id and penalty.get("state") == "paused":
                    # Resume penalty timer
                    timer_manager.resume_timer(penalty_id)
                    penalty["state"] = "running"
                    Settings.update_penalty_timer(penalty_id, penalty)
        else:
            # Penalty timer resumed
            _penalties = current_timers.get("penalties", {"home": [], "away": []})
            penalties = _penalties['home'] + _penalties['away']
            for penalty in penalties:
                if penalty.get("timer_id") == timer_id:
                    penalty["state"] = "running"
                    Settings.update_penalty_timer(timer_id, penalty)
                    break
        
        emit('timer_resumed', {'timer_id': timer_id}, broadcast=True)
    else:
        emit('error', {'message': f'Failed to resume timer {timer_id}'})


@socketio.on('timer_reset')
def handle_timer_reset(data):
    """
    Reset timer.
    Does NOT emit timer_reset to UI directly — the confirmation comes from
    timer-plugin → hub_client → timer_manager.on_timer_reset → _emit_to_ui.

    Client sends: {'timer_id': 'match-123'}
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return

    timer_id = data.get('timer_id')
    success = timer_manager.reset_timer(timer_id)

    if not success:
        emit('error', {'message': f'Failed to reset timer {timer_id}'})
        
@socketio.on('timer_remove')
def handle_timer_remove(data):
    """
    Remove a timer from both Timer Plugin and Settings
    
    Client sends: {'timer_id': 'penalty_home_123'}
    """
    from app.models.settings import Settings
    from flask import current_app
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    current_app.logger.info(f"🗑️  Attempting to remove timer: {timer_id}")
    
    # Remove from Timer Plugin
    success = timer_manager.remove_timer(timer_id)
    current_app.logger.info(f"Timer Plugin remove_timer result: {success}")
    
    if success:
        # Remove from Settings.current_timers
        current_timers = Settings.get_current_timers()
        penalties = current_timers.get("penalties", {"home": [], "away": []})
        # home_penalties = penalties['home']
        # away_penalties = penalties['away']        
        current_app.logger.info(f"Current home penalties before removal: {[p.get('timer_id') for p in penalties['home']]}")
        current_app.logger.info(f"Current away penalties before removal: {[p.get('timer_id') for p in penalties['away']]}")
        
        # Filter out the removed penalty
        updated_home_penalties = [p for p in penalties['home'] if p.get("timer_id") != timer_id]
        updated_away_penalties = [p for p in penalties['away'] if p.get("timer_id") != timer_id]
        
        if len(updated_home_penalties + updated_away_penalties) < len(penalties):
            # Penalty was found and removed
            current_timers["penalties"]["home"] = updated_home_penalties
            current_timers["penalties"]["away"] = updated_away_penalties
            Settings.set_current_timers(current_timers)
            home_penalties = current_timers['penalties']['home']
            away_penalties = current_timers['penalties']['away']
            penalties = {'home': home_penalties, 'away': away_penalties}
            
            current_app.logger.info(f"✅ Penalty removed from Settings: {timer_id}")
            # emit('timer_removed', {'timer_id': timer_id}, broadcast=True)
            emit('reload_penalty_timers', {'penalties': penalties}, broadcast=True)
            return True
        else:
            # Timer not found in penalties (might be main timer - don't allow removal)
            current_app.logger.warning(f"⚠️  Timer {timer_id} not found in penalties")
            emit('error', {'message': 'Cannot remove main timer or timer not found'})
            return False
    else:
        current_app.logger.error(f"❌ Timer Plugin failed to remove timer: {timer_id}")
        emit('error', {'message': f'Failed to remove timer {timer_id} from Timer Plugin'})
        return False

# @socketio.on('timer_stop')
# def handle_timer_stop(data):
#     """
#     Stop a timer
#
#     Client sends: {'timer_id': 'match-123'}
#     """
#     timer_manager = get_timer_manager()
#     if not timer_manager:
#         emit('error', {'message': 'Timer manager not available'})
#         return
#
#     timer_id = data.get('timer_id')
#     success = timer_manager.stop_timer(timer_id)
#
#     if success:
#         emit('timer_stopped', {'timer_id': timer_id}, broadcast=True)
#     else:
#         emit('error', {'message': f'Failed to stop timer {timer_id}'})


# ============================================================================
# TIME SYNCHRONIZATION (Buttons +/-)
# ============================================================================

@socketio.on('timer_adjust')
def handle_timer_adjust(data):
    """
    Adjust timer time by offset
    
    Client sends:
    {
        'timer_id': 'match-123',
        'delta': 60000  // +1 minute
    }
    
    or
    
    {
        'timer_id': 'match-123',
        'delta': -10000  // -10 seconds
    }
    """
    from app.models.settings import Settings
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    delta = data.get('delta', 0)
    
    success = timer_manager.adjust_time(timer_id, delta)
    
    if success:
        # Check if this is the main timer
        current_timers = Settings.get_current_timers()
        main_timer = current_timers.get("main")
        
        if main_timer and main_timer.get("timer_id") == timer_id:
            # Update main timer state in Settings
            timer_state = timer_manager.get_timer_state(timer_id)
            if timer_state:
                main_timer["state"] = timer_state.get("state", main_timer.get("state"))
                main_timer["elapsed_time"] = timer_state.get("elapsed_time", main_timer.get("elapsed_time", 0))
                Settings.update_main_timer(main_timer)
                
                # If main timer was adjusted back from limit_reached, update penalties
                # Penalties will be adjusted automatically by timer plugin (dependent timers)
        else:
            # This is a penalty timer - update its state in Settings
            _penalties = current_timers.get("penalties", {"home": [], "away": []})
            penalties = _penalties['home'] + _penalties['away']
            for penalty in penalties:
                if penalty.get("timer_id") == timer_id:
                    timer_state = timer_manager.get_timer_state(timer_id)
                    if timer_state:
                        penalty["state"] = timer_state.get("state", penalty.get("state"))
                        penalty["elapsed_time"] = timer_state.get("elapsed_time", penalty.get("elapsed_time", 0))
                        Settings.update_penalty_timer(timer_id, penalty)
                    break
        
        emit('timer_adjusted', {
            'timer_id': timer_id,
            'delta': delta
        }, broadcast=True)
    else:
        emit('error', {'message': f'Failed to adjust timer {timer_id}'})


@socketio.on('timer_set_time')
def handle_timer_set_time(data):
    """
    Set specific elapsed time
    
    Client sends:
    {
        'timer_id': 'match-123',
        'elapsed_time': 750000  // Set to 12:30
    }
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    elapsed_time = data.get('elapsed_time', 0)
    
    success = timer_manager.set_elapsed_time(timer_id, elapsed_time)
    
    if success:
        emit('timer_time_set', {
            'timer_id': timer_id,
            'elapsed_time': elapsed_time
        }, broadcast=True)
    else:
        emit('error', {'message': f'Failed to set time for timer {timer_id}'})


# ============================================================================
# HIGH-LEVEL MATCH OPERATIONS
# ============================================================================

@socketio.on('match_timer_create')
def handle_game_timer_create(data):
    """
    Create match timer with penalty support
    
    Client sends:
    {
        'game_id': 123,
        'duration_minutes': 40
    }
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    game_id = data.get('game_id')
    duration_minutes = data.get('duration_minutes', 40)
    
    timer_id = timer_manager.create_game_timer(game_id, duration_minutes)
    
    emit('match_timer_created', {
        'game_id': game_id,
        'timer_id': timer_id
    }, broadcast=True)


@socketio.on('penalty_timer_create')
def handle_penalty_timer_create(data):
    """
    Create penalty timer (dependent on match timer)
    
    Client sends:
    {
        'game_timer_id': 'match-123',
        'team': 'home' or 'away',
        'team_name': 'Torpedo Zielona Góra',
        'duration_minutes': 2
    }
    """
    from app.models.settings import Settings
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    game_timer_id = data.get('game_timer_id')
    team = data.get('team', 'home')  # 'home' or 'away'
    team_name = data.get('team_name', '')
    duration_minutes = data.get('duration_minutes', 2)

    all_current_penalties_timers = Settings.get_current_timers()['penalties']
    current_penalties_timers = all_current_penalties_timers['home'] + all_current_penalties_timers['away']
    team_penalties_timers_number = 0
    for timer in current_penalties_timers:
        print(f'timer in current: {timer}')
        if timer and timer['timer_id'].startswith(f'penalty_{team}'):
            team_penalties_timers_number += 1

    if team_penalties_timers_number < 2:
        # Generate unique penalty timer ID
        import time
        penalty_timer_id = f"penalty_{team}_{int(time.time() * 1000)}"
        
        # Create penalty timer
        timer_manager.create_timer(
            timer_id=penalty_timer_id,
            timer_type='dependent',
            parent_id=game_timer_id,
            initial_time=0,
            limit=duration_minutes * 60000,  # Convert to milliseconds
            pause_at_limit=True,
            metadata={
                'team': team,
                'team_name': team_name,
                'timer_class': 'penalty',
                'duration_minutes': duration_minutes
            }
        )
    
@socketio.on('change_game_value')
def handle_change_game_value(data):
    from app.models.settings import Settings
    from app.models.game import Game
    from app.managers.period_manager import PeriodManager

    period_manager = PeriodManager()
    current_game_id = Settings.get_settings().current_game_id
    current_period_id = period_manager.get_current_period(current_game_id).id
    team_type = data.get('team_type')
    value_type = data.get('value_type')
    value = data.get('value')
    period = None

    if value_type == "score":
        period = period_manager.increment_period_goal(current_period_id, team_type, value)
    elif value_type == "fouls":
        period = period_manager.increment_period_foul(current_period_id, team_type, value)

    if period:
        game = Game.query.filter_by(id=period.game_id).first()
        data = {
            'home_team_goals': game.home_team_goals,
            'home_team_fouls': game.home_team_fouls,
            'away_team_goals': game.away_team_goals,
            'away_team_fouls': game.away_team_fouls,
        }
        hub_client = get_hub_client()
        if hub_client:
            hub_client.broadcast_to_class('game_data_receiver', 'scoreboard_data', data)
            emit('scoreboard_data', {'payload': data})

@socketio.on('request_ui_monitor_content')
def handle_request_ui_monitor_content(data):
    print('handle_show_ui_monitor_content data', data)
    content_type = data.get('type')
    if content_type == None:
        emit('show_ui_monitor_content', {'content_type': None})
    elif content_type == 'events':
        from app.managers.event_manager import EventManager
        event_manager = EventManager()
        events_types = event_manager.get_all_events()
        _events_types = []
        for event in events_types:
            _events_types.append(event.to_dict())
        from app.managers.game_event_manager import GameEventManager
        game_event_manager = GameEventManager()
        from app.models.settings import Settings
        settings = Settings.get_settings()
        current_game_id = settings.current_game_id
        game_events = game_event_manager.get_events_for_game(current_game_id)
        _game_events = []
        for event in game_events:
            _game_events.append(event.to_dict())
        emit('show_ui_monitor_content', {'content_type': 'events',
                                         'events_types': _events_types,
                                         'game_events': _game_events})
    elif content_type == 'edit_event':
        payload = data.get('payload')
        game_event_id = payload['game_event_id']
        from app.managers.event_manager import EventManager
        event_manager = EventManager()
        events_types = event_manager.get_all_events()
        _events_types = []
        for event in events_types:
            if event.filter_class:
                _events_types.append(event.to_dict())
        from app.managers.game_event_manager import GameEventManager
        game_event_manager = GameEventManager()
        game_event = game_event_manager.get_game_event_by_id(game_event_id)
        game_id = game_event.game_id
        from app.managers.game_manager import GameManager
        game_manager = GameManager()
        game_data = game_manager.get_game_by_id(game_id).to_dict()
        from app.models.settings import Settings
        settings = Settings.get_settings()
        is_scoreboard_reversed = settings.is_scoreboard_reversed

        emit('show_ui_monitor_content', {'content_type': 'edit_event',
                                         'events_types': _events_types,
                                         'game_data': game_data,
                                         'is_scoreboard_reversed': bool(is_scoreboard_reversed),
                                         'game_event': game_event.to_dict()})


    
    # # ALWAYS sync penalty state with parent state
    # parent_state = timer_manager.get_timer_state(game_timer_id)
    
    # if parent_state:
    #     # Copy parent's state to penalty
    #     current_parent_state = parent_state.get('state', 'idle')
        
    #     if current_parent_state == 'running':
    #         # Parent is running - start penalty immediately
    #         timer_manager.start_timer(penalty_timer_id)
    #         penalty_state = 'running'
    #     elif current_parent_state == 'paused':
    #         # Parent is paused - start penalty then immediately pause it
    #         timer_manager.start_timer(penalty_timer_id)
    #         timer_manager.pause_timer(penalty_timer_id)
    #         penalty_state = 'paused'
    #     else:
    #         # Parent is idle or other state
    #         penalty_state = current_parent_state
    # else:
    #     # No parent state found - default to idle
    #     penalty_state = 'idle'
    
    # # Add to Settings.current_timers
    # penalty_data = {
    #     "timer_id": penalty_timer_id,
    #     "timer_type": "dependent",
    #     "parent_id": game_timer_id,
    #     "initial_time": 0,
    #     "limit": duration_minutes * 60000,
    #     "state": penalty_state,
    #     "metadata": {
    #         "team": team,
    #         "team_name": team_name,
    #         "timer_class": "penalty",
    #         "duration_minutes": duration_minutes
    #     }
    # }
    # Settings.add_penalty_timer(penalty_data)
    
    # emit('penalty_timer_created', {
    #     'timer_id': penalty_timer_id,
    #     'team': team,
    #     'team_name': team_name
    # }, broadcast=True)


# ============================================================================
# RAFTING OPERATIONS
# ============================================================================

@socketio.on('rafting_timer_create')
def handle_rafting_timer_create(data):
    """
    Create rafting timer
    
    Client sends:
    {
        'team_name': 'Team Alpha',
        'start_number': 1
    }
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    team_name = data.get('team_name')
    start_number = data.get('start_number')
    
    timer_id = timer_manager.create_rafting_timer(team_name, start_number)
    
    emit('rafting_timer_created', {
        'timer_id': timer_id,
        'team_name': team_name,
        'start_number': start_number
    }, broadcast=True)


# ============================================================================
# SKIING OPERATIONS
# ============================================================================

@socketio.on('skiing_timers_create')
def handle_skiing_timers_create(data):
    """
    Create parallel skiing timers
    
    Client sends:
    {
        'skier_blue': {'name': 'Jan Kowalski', 'country': 'POL'},
        'skier_red': {'name': 'Anna Nowak', 'country': 'POL'}
    }
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    skier_blue = data.get('skier_blue', {})
    skier_red = data.get('skier_red', {})
    
    blue_id, red_id = timer_manager.create_parallel_skiing_timers(
        skier_blue,
        skier_red
    )
    
    emit('skiing_timers_created', {
        'blue_timer_id': blue_id,
        'red_timer_id': red_id
    }, broadcast=True)


@socketio.on('skiing_start_simultaneous')
def handle_skiing_start_simultaneous(data):
    """
    Start both skiing timers simultaneously
    
    Client sends:
    {
        'blue_timer_id': 'ski-blue-123',
        'red_timer_id': 'ski-red-456'
    }
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    blue_id = data.get('blue_timer_id')
    red_id = data.get('red_timer_id')
    
    success = timer_manager.start_multiple([blue_id, red_id])
    
    if success:
        emit('skiing_started', {
            'blue_timer_id': blue_id,
            'red_timer_id': red_id
        }, broadcast=True)
    else:
        emit('error', {'message': 'Failed to start skiing timers'})


# ============================================================================
# QUERY OPERATIONS
# ============================================================================

@socketio.on('timer_get_state')
def handle_timer_get_state(data):
    """
    Get timer state from cache
    
    Client sends: {'timer_id': 'match-123'}
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    state = timer_manager.get_timer_state(timer_id)
    
    if state:
        emit('timer_state', state)
    else:
        emit('error', {'message': f'Timer {timer_id} not found'})


@socketio.on('timers_get_all')
def handle_timers_get_all():
    """Get all timers from cache"""
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_manager.get_all_timers()
    
    # emit('timers_list', {
    #     'timers': list(timers.values()),
    #     'count': len(timers)
    # })

# @socketio.on('timer_plugin_request_all_timers')
# def handle_timer_plugin_request_all_timers():
#     """
#     Request all timers from timer-plugin
#     UI will use this to check which timers are running after crash/restart
    
#     Flow:
#     1. UI sends 'timer_plugin_request_all_timers'
#     2. Backend sends request to timer-plugin via hub
#     3. Timer-plugin responds via hub -> backend
#     4. Backend emits 'timer_plugin_all_timers' back to UI
#     """
#     current_app.logger.info('📥 UI requested all timers from plugin')
    
#     timer_manager = get_timer_manager()
#     if not timer_manager:
#         emit('error', {'message': 'Timer manager not available'})
#         return
    
#     # Send request to timer-plugin
#     # The response will come via hub message handler
#     timer_manager.get_all_timers()
#     current_app.logger.info('📤 Request sent to timer-plugin')


# @socketio.on('timer_plugin_create_timer')
# def handle_timer_plugin_create_timer(data):
#     """
#     Create timer in timer-plugin (recovery)
    
#     Client sends:
#     {
#         'timer_id': 'main-p1',
#         'timer_type': 'independent',
#         'initial_time': 0,
#         'limit': 1200000,
#         'pause_at_limit': true,
#         'metadata': {...}
#     }
#     """
#     current_app.logger.info(f'📥 UI requested timer creation: {data.get("timer_id")}')
    
#     timer_manager = get_timer_manager()
#     if not timer_manager:
#         emit('error', {'message': 'Timer manager not available'})
#         return
    
#     timer_id = data.get('timer_id')
#     timer_type = data.get('timer_type', 'independent')
    
#     # Extract parameters
#     kwargs = {}
#     if 'parent_id' in data:
#         kwargs['parent_id'] = data['parent_id']
#     if 'limit' in data:
#         kwargs['limit'] = data['limit']
#     if 'pause_at_limit' in data:
#         kwargs['pause_at_limit'] = data['pause_at_limit']
#     if 'initial_time' in data:
#         kwargs['initial_time'] = data['initial_time']
#     if 'metadata' in data:
#         kwargs['metadata'] = data['metadata']
    
#     success = timer_manager.create_timer(timer_id, timer_type, **kwargs)
    
#     if success:
#         current_app.logger.info(f'✅ Timer created: {timer_id}')
#     else:
#         current_app.logger.error(f'❌ Failed to create timer: {timer_id}')
#         emit('error', {'message': f'Failed to create timer {timer_id}'})


# @socketio.on('timer_plugin_start_timer')
# def handle_timer_plugin_start_timer(data):
#     """
#     Start timer in timer-plugin (recovery)
    
#     Client sends: {'timer_id': 'main-p1'}
#     """
#     current_app.logger.info(f'📥 UI requested timer start: {data.get("timer_id")}')
    
#     timer_manager = get_timer_manager()
#     if not timer_manager:
#         emit('error', {'message': 'Timer manager not available'})
#         return
    
#     timer_id = data.get('timer_id')
#     success = timer_manager.start_timer(timer_id)
    
#     if success:
#         current_app.logger.info(f'✅ Timer started: {timer_id}')
#     else:
#         current_app.logger.error(f'❌ Failed to start timer: {timer_id}')
#         emit('error', {'message': f'Failed to start timer {timer_id}'})

@socketio.on('timer_plugin_request_all_timers')
def handle_timer_plugin_request_all_timers():
    """
    Request all timers from timer-plugin
    UI will use this to check which timers are running after crash/restart
    
    Flow:
    1. UI sends 'timer_plugin_request_all_timers' via socket
    2. Backend calls timer_manager.get_all_timers()
    3. Timer manager sends request to timer-plugin via hub
    4. Timer-plugin responds with list of all timers
    5. Hub forwards response to backend
    6. Backend's on_all_timers() emits 'timer_plugin_all_timers' to UI
    
    Note: This handler doesn't wait for response - it's async.
    Response comes via different path (hub -> timer_manager -> socketio emit)
    """
    current_app.logger.info('📥 UI requested all timers from plugin')
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    # Send request to timer-plugin
    # The response will come via hub message handler -> on_all_timers()
    success = timer_manager.get_all_timers()
    if success:
        current_app.logger.info('📤 Request sent to timer-plugin')
    else:
        # Plugin is offline - inform UI immediately so it doesn't wait for timeout
        emit('timer_plugin_offline', {'message': 'Timer plugin is not connected'})


@socketio.on('timer_plugin_create_timer')
def handle_timer_plugin_create_timer(data):
    """
    Create timer in timer-plugin (used during recovery)
    
    Client sends:
    {
        'timer_id': 'main-p1',
        'timer_type': 'independent',  # or 'dependent'
        'initial_time': 0,
        'limit': 1200000,
        'pause_at_limit': true,
        'parent_id': 'main-p1',  # only for dependent timers
        'metadata': {
            'description': '1. połowa',
            'period': 1,
            'timer_class': 'main'
        }
    }
    
    This is called when recovery system detects a timer is missing
    in timer-plugin but exists in Settings.current_timers
    """
    current_app.logger.info(f'📥 UI requested timer creation: {data.get("timer_id")}')
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    timer_type = data.get('timer_type', 'independent')
    
    # Extract optional parameters
    kwargs = {}
    if 'parent_id' in data:
        kwargs['parent_id'] = data['parent_id']
    if 'limit' in data:
        kwargs['limit'] = data['limit']
    if 'pause_at_limit' in data:
        kwargs['pause_at_limit'] = data['pause_at_limit']
    if 'initial_time' in data:
        kwargs['initial_time'] = data['initial_time']
    if 'metadata' in data:
        kwargs['metadata'] = data['metadata']
    
    success = timer_manager.create_timer(timer_id, timer_type, **kwargs)
    
    if success:
        current_app.logger.info(f'✅ Timer created: {timer_id}')
    else:
        current_app.logger.error(f'❌ Failed to create timer: {timer_id}')
        emit('error', {'message': f'Failed to create timer {timer_id}'})


@socketio.on('timer_plugin_start_timer')
def handle_timer_plugin_start_timer(data):
    """
    Start timer in timer-plugin (used during recovery)
    
    Client sends: 
    {
        'timer_id': 'main-p1'
    }
    
    This is called after creating a timer that was in 'running' state
    before the crash. The recovery system creates the timer first,
    then starts it to restore the previous state.
    """
    current_app.logger.info(f'📥 UI requested timer start: {data.get("timer_id")}')
    
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    success = timer_manager.start_timer(timer_id)
    
    if success:
        current_app.logger.info(f'✅ Timer started: {timer_id}')
    else:
        current_app.logger.error(f'❌ Failed to start timer: {timer_id}')
        emit('error', {'message': f'Failed to start timer {timer_id}'})

@socketio.on('trigger_sequence')
def handle_trigger_sequence(data):
    sequence_manager = get_sequence_manager()
    sequence_id = sequence_manager.trigger(data['sequence'], data.get('context', {}))
    emit('sequence_started', {'sequence_id': sequence_id})

@socketio.on('stop_sequence')
def handle_stop_sequence(data):
    sequence_id = data.get('sequence_id')
    sequence_manager = get_sequence_manager()
    if sequence_id:
        sequence_manager.stop(sequence_id)
        emit('sequence_stopped', {'sequence_id': sequence_id})
    else:
        # zatrzymaj wszystkie instancje danej sekwencji
        sequence_manager.stop_all(data.get('sequence'))
        emit('all_sequences_stopped', {})

# ============================================================================
# GAME EVENTS
# ============================================================================

@socketio.on('add_game_event_to_db')
def handle_add_game_event_to_db(data):

    from app.models.settings import Settings
    from app.models.game import Game
    from app.managers.period_manager import PeriodManager
    from app.models.team import Team
    from app.managers.game_event_manager import GameEventManager
    from app.managers import get_timer_manager
    from app.managers import get_hub_client

    settings = Settings.get_settings()
    game_id   = settings.current_game_id
    period_id = settings.current_period_id
    timer_id = settings.get_current_timers()['main']['timer_id']

    if not game_id or not period_id:
        emit('error', {'message': 'Brak aktywnego meczu lub okresu'})
        return
    period_manager = PeriodManager()
    current_period_data = period_manager.get_period_by_id(period_id=period_id).to_dict()
    current_period_initial_time_in_seconds = int(current_period_data['initial_time_seconds'])
    timer_manager = get_timer_manager()
    timer_state = timer_manager.get_timer_state(timer_id=timer_id)
    elapsed_seconds = int(timer_state['elapsed_time']/1000)
    game_time = elapsed_seconds + current_period_initial_time_in_seconds
    # Resolve team_id from team_type ('home'/'away')
    team_id = None
    team_type = data.get('team_type')
    if team_type in ('home', 'away'):
        game = Game.query.get(game_id)
        if game:
            team_id = game.home_team_id if team_type == 'home' else game.away_team_id

    event_type     = data.get('event_type')
    selected_cell  = data.get('selected_cell_id')


    print(f'elapsed_seconds: {elapsed_seconds} - typ {type(elapsed_seconds)},')
    print(f'current_period_initial_time_in_seconds: {current_period_initial_time_in_seconds} - typ {type(current_period_initial_time_in_seconds)},')
    print(f'game_time: {game_time} - typ {type(game_time)},')

    try:
        manager = GameEventManager()
        game_event = manager.record_event(
            game_id=game_id,
            event_id=_resolve_event_id(event_type),
            period_id=period_id,
            team_id=team_id,
            event_place=selected_cell,
            game_time=game_time,
        )
    except Exception as e:
        current_app.logger.error(f'❌ Failed to save game event: {e}')
        emit('error', {'message': str(e)})
        return

    # current_app.logger.info(f'✅ GameEvent saved: id={game_event.id} type={event_type}')

    # # Notify UI
    # emit('game_event_saved', {'game_event_id': game_event.id}, broadcast=True)

    # Request recording data from all recorder_device plugins
    hub_client = get_hub_client()
    if hub_client:
        # hub_client.broadcast_to_class(class_name='recorder_device', msg_type='recording_command', payload={
        hub_client.broadcast(msg_type='recording_command', payload={
            'requestType': 'GetRecordStatus',
            'requestData': {},
            'request_id': 'get-record-status-' + str(game_event.id),
            'game_event_id': game_event.id,
            'cameras':{'camera1': True,
                       'camera2': False,
                       'camera3': False,
                       'camera4': False}})
        current_app.logger.info(
            f'📡 Sent get_record_file_info to recorder_device for game_event_id={game_event.id}'
        )


def _resolve_event_id(event_type: str):
    """
    Resolve event_type string to Event.id from DB.
    Looks up by Event.short_name (case-insensitive).
    Raises ValueError if not found.
    """
    from app.models.event import Event
    event = Event.query.filter(
        Event.name.ilike(event_type)
    ).first()
    if not event:
        raise ValueError(f"Nieznany typ zdarzenia: '{event_type}'")
    return event.id 