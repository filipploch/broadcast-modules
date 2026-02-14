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
            penalties = current_timers.get("penalties", [])
            for penalty in penalties:
                penalty_id = penalty.get("timer_id")
                if penalty_id:
                    # Start penalty timer
                    timer_manager.start_timer(penalty_id)
                    penalty["state"] = "running"
                    Settings.update_penalty_timer(penalty_id, penalty)
        else:
            # Penalty timer started
            penalties = current_timers.get("penalties", [])
            for penalty in penalties:
                if penalty.get("timer_id") == timer_id:
                    penalty["state"] = "running"
                    Settings.update_penalty_timer(timer_id, penalty)
                    break
        
        emit('timer_started', {'timer_id': timer_id}, broadcast=True)
    else:
        emit('error', {'message': f'Failed to start timer {timer_id}'})


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
            main_timer["initial_time"] = timer_state.get("elapsed_time", main_timer.get("initial_time", 0))
            Settings.update_main_timer(main_timer)
            
            # Pause all penalty timers (dependent)
            penalties = current_timers.get("penalties", [])
            for penalty in penalties:
                penalty_id = penalty.get("timer_id")
                if penalty_id:
                    # Pause penalty timer
                    timer_manager.pause_timer(penalty_id)
                    penalty_state = timer_manager.get_timer_state(penalty_id)
                    if penalty_state:
                        penalty["state"] = "paused"
                        penalty["initial_time"] = penalty_state.get("elapsed_time", penalty.get("initial_time", 0))
                        Settings.update_penalty_timer(penalty_id, penalty)
    else:
        # Penalty timer paused
        penalties = current_timers.get("penalties", [])
        for penalty in penalties:
            if penalty.get("timer_id") == timer_id:
                timer_state = timer_manager.get_timer_state(timer_id)
                if timer_state:
                    penalty["state"] = "paused"
                    penalty["initial_time"] = timer_state.get("elapsed_time", penalty.get("initial_time", 0))
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
            penalties = current_timers.get("penalties", [])
            for penalty in penalties:
                penalty_id = penalty.get("timer_id")
                if penalty_id and penalty.get("state") == "paused":
                    # Resume penalty timer
                    timer_manager.resume_timer(penalty_id)
                    penalty["state"] = "running"
                    Settings.update_penalty_timer(penalty_id, penalty)
        else:
            # Penalty timer resumed
            penalties = current_timers.get("penalties", [])
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
        penalties = current_timers.get("penalties", [])
        
        current_app.logger.info(f"Current penalties before removal: {[p.get('timer_id') for p in penalties]}")
        
        # Filter out the removed penalty
        updated_penalties = [p for p in penalties if p.get("timer_id") != timer_id]
        
        if len(updated_penalties) < len(penalties):
            # Penalty was found and removed
            current_timers["penalties"] = updated_penalties
            Settings.set_current_timers(current_timers)
            
            current_app.logger.info(f"✅ Penalty removed from Settings: {timer_id}")
            emit('timer_removed', {'timer_id': timer_id}, broadcast=True)
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
                main_timer["initial_time"] = timer_state.get("elapsed_time", main_timer.get("initial_time", 0))
                Settings.update_main_timer(main_timer)
                
                # If main timer was adjusted back from limit_reached, update penalties
                # Penalties will be adjusted automatically by timer plugin (dependent timers)
        else:
            # This is a penalty timer - update its state in Settings
            penalties = current_timers.get("penalties", [])
            for penalty in penalties:
                if penalty.get("timer_id") == timer_id:
                    timer_state = timer_manager.get_timer_state(timer_id)
                    if timer_state:
                        penalty["state"] = timer_state.get("state", penalty.get("state"))
                        penalty["initial_time"] = timer_state.get("elapsed_time", penalty.get("initial_time", 0))
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
        'match_timer_id': 'match-123',
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
    
    match_timer_id = data.get('match_timer_id')
    team = data.get('team', 'home')  # 'home' or 'away'
    team_name = data.get('team_name', '')
    duration_minutes = data.get('duration_minutes', 2)
    
    # Generate unique penalty timer ID
    import time
    penalty_timer_id = f"penalty_{team}_{int(time.time() * 1000)}"
    
    # Create penalty timer
    timer_manager.create_timer(
        timer_id=penalty_timer_id,
        timer_type='dependent',
        parent_id=match_timer_id,
        initial_time=0,
        limit_time=duration_minutes * 60000,  # Convert to milliseconds
        pause_at_limit=True,
        metadata={
            'team': team,
            'team_name': team_name,
            'timer_class': 'penalty',
            'duration_minutes': duration_minutes
        }
    )
    
    # ALWAYS sync penalty state with parent state
    parent_state = timer_manager.get_timer_state(match_timer_id)
    
    if parent_state:
        # Copy parent's state to penalty
        current_parent_state = parent_state.get('state', 'idle')
        
        if current_parent_state == 'running':
            # Parent is running - start penalty immediately
            timer_manager.start_timer(penalty_timer_id)
            penalty_state = 'running'
        elif current_parent_state == 'paused':
            # Parent is paused - start penalty then immediately pause it
            timer_manager.start_timer(penalty_timer_id)
            timer_manager.pause_timer(penalty_timer_id)
            penalty_state = 'paused'
        else:
            # Parent is idle or other state
            penalty_state = current_parent_state
    else:
        # No parent state found - default to idle
        penalty_state = 'idle'
    
    # Add to Settings.current_timers
    penalty_data = {
        "timer_id": penalty_timer_id,
        "timer_type": "dependent",
        "parent_id": match_timer_id,
        "initial_time": 0,
        "limit_time": duration_minutes * 60000,
        "state": penalty_state,
        "metadata": {
            "team": team,
            "team_name": team_name,
            "timer_class": "penalty",
            "duration_minutes": duration_minutes
        }
    }
    Settings.add_penalty_timer(penalty_data)
    
    emit('penalty_timer_created', {
        'timer_id': penalty_timer_id,
        'team': team,
        'team_name': team_name
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