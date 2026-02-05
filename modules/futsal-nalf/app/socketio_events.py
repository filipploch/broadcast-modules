"""SocketIO events - MINIMAL"""
from flask import current_app
from flask_socketio import emit
from app.extensions import socketio
from app.managers import get_hub_client
from app.managers import get_timer_manager

@socketio.on('connect')
def handle_connect():
    current_app.logger.info('🔌 UI client connected')
    emit('connected', {'status': 'ok'})

@socketio.on('disconnect')
def handle_disconnect():
    current_app.logger.info('🔌 UI client disconnected')

@socketio.on('start_recording')
def handle_start_recording():
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast('start_recording', {'cameras': []})
        emit('recording_started', {}, broadcast=True)

@socketio.on('stop_recording')
def handle_stop_recording():
    hub_client = get_hub_client()
    if hub_client:
        hub_client.broadcast('stop_recording', {})
        emit('recording_stopped', {}, broadcast=True)

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
        'limit_time': 2400000,
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
    if 'limit_time' in data:
        kwargs['limit_time'] = data['limit_time']
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
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    timer_id = data.get('timer_id')
    success = timer_manager.start_timer(timer_id)
    
    if success:
        emit('timer_started', {'timer_id': timer_id}, broadcast=True)
    else:
        emit('error', {'message': f'Failed to start timer {timer_id}'})


@socketio.on('timer_pause')
def handle_timer_pause(data):
    """
    Pause a timer
    
    Client sends: {'timer_id': 'match-123'}
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    timer_manager.pause_timer(timer_id)
    
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
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    success = timer_manager.resume_timer(timer_id)
    
    if success:
        emit('timer_resumed', {'timer_id': timer_id}, broadcast=True)
    else:
        emit('error', {'message': f'Failed to resume timer {timer_id}'})


@socketio.on('timer_reset')
def handle_timer_reset(data):
    """
    Reset timer

    Client sends: {'timer_id': 'match-123'}
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return

    timer_id = data.get('timer_id')
    success = timer_manager.reset_timer(timer_id)

    if success:
        emit('timer_reset', {'timer_id': timer_id}, broadcast=True)
    else:
        emit('error', {'message': f'Failed to reset timer {timer_id}'})

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
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    timer_id = data.get('timer_id')
    delta = data.get('delta', 0)
    
    success = timer_manager.adjust_time(timer_id, delta)
    
    if success:
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
def handle_match_timer_create(data):
    """
    Create match timer with penalty support
    
    Client sends:
    {
        'match_id': 123,
        'duration_minutes': 40
    }
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    match_id = data.get('match_id')
    duration_minutes = data.get('duration_minutes', 40)
    
    timer_id = timer_manager.create_match_timer(match_id, duration_minutes)
    
    emit('match_timer_created', {
        'match_id': match_id,
        'timer_id': timer_id
    }, broadcast=True)


@socketio.on('penalty_timer_create')
def handle_penalty_timer_create(data):
    """
    Create penalty timer (dependent on match timer)
    
    Client sends:
    {
        'match_timer_id': 'match-123',
        'player_number': 7,
        'player_name': 'Jan Kowalski',
        'duration_minutes': 2
    }
    """
    timer_manager = get_timer_manager()
    if not timer_manager:
        emit('error', {'message': 'Timer manager not available'})
        return
    
    match_timer_id = data.get('match_timer_id')
    player_info = {
        'number': data.get('player_number'),
        'name': data.get('player_name')
    }
    duration_minutes = data.get('duration_minutes', 2)
    
    timer_id = timer_manager.create_penalty_timer(
        match_timer_id,
        player_info,
        duration_minutes
    )
    
    emit('penalty_timer_created', {
        'timer_id': timer_id,
        'player_info': player_info
    }, broadcast=True)


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
