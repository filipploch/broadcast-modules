"""Timer Manager - Manages timer plugin communication and state"""
from flask import current_app
from datetime import datetime
from app.models import Settings
# from app.managers import get_timer_manager
import threading


class TimerManager:
    """Manages communication with Timer Plugin and caches timer states"""
    
    def __init__(self, hub_client):
        """
        Initialize Timer Manager
        
        Args:
            hub_client: HubClient instance for WebSocket communication
        """
        self.hub_client = hub_client
        # plugin_manager = get_timer_manager()
        self.timer_plugin_id = 'timer-plugin'
        self.timers = {}  # Cache: {timer_id: timer_state}
        self.lock = threading.Lock()
        
        current_app.logger.info("TimerManager initialized")
    
    # ========================================================================
    # TIMER LIFECYCLE
    # ========================================================================
    
    def create_timer(self, timer_id, timer_type='independent', **kwargs):
        """
        Create a new timer
        
        Args:
            timer_id: Unique timer identifier
            timer_type: 'independent' or 'dependent'
            **kwargs: Additional timer config (parent_id, limit, etc.)
        
        Returns:
            bool: Success status
        """
        payload = {
            'timer_id': timer_id,
            'timer_type': timer_type,
            **kwargs
        }

        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'create_timer',
            payload
        )
        
        if success:
            # Initialize cache
            with self.lock:
                self.timers[timer_id] = {
                    'timer_id': timer_id,
                    'timer_type': timer_type,
                    'state': 'idle',
                    'initial_time': kwargs.get('initial_time'),
                    'metadata': kwargs.get('metadata', {}),
                    'parent_id': kwargs.get('parent_id'),
                    'limit': kwargs.get('limit'),
                }
            
            current_app.logger.info(f"✅ Created timer: {timer_id} ({timer_type})")
        else:
            current_app.logger.error(f"❌ Failed to create timer: {timer_id}")
        
        return success
    
    def start_timer(self, timer_id):
        """Start a timer"""
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'start_timer',
            {'timer_id': timer_id}
        )
        
        if success:
            with self.lock:
                if timer_id in self.timers:
                    self.timers[timer_id]['state'] = 'running'
            current_app.logger.info(f"▶️  Started timer: {timer_id}")
        
        return success
    
    def pause_timer(self, timer_id):
        """Pause a timer"""
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'pause_timer',
            {'timer_id': timer_id}
        )
        
        if success:
            with self.lock:
                if timer_id in self.timers:
                    self.timers[timer_id]['state'] = 'paused'
            current_app.logger.info(f"⏸️  Paused timer: {timer_id}")

    def resume_timer(self, timer_id):
        """Resume a paused timer"""
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'resume_timer',
            {'timer_id': timer_id}
        )
        
        if success:
            with self.lock:
                if timer_id in self.timers:
                    self.timers[timer_id]['state'] = 'running'
            current_app.logger.info(f"▶️  Resumed timer: {timer_id}")
        
        return success
    
    def reset_timer(self, timer_id):
        """Reset a timer"""
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'reset_timer',
            {'timer_id': timer_id}
        )
        
        if success:
            with self.lock:
                if timer_id in self.timers:
                    self.timers[timer_id]['state'] = 'idle'
            current_app.logger.info(f"⏹️  Reseted timer: {timer_id}")
        
        return success
    
    def remove_timer(self, timer_id):
        """Remove a timer"""
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'remove_timer',
            {'timer_id': timer_id}
        )
        
        if success:
            with self.lock:
                if timer_id in self.timers:
                    del self.timers[timer_id]
            current_app.logger.info(f"🗑️  Removed timer: {timer_id}")
        
        return success
    
    # ========================================================================
    # TIME SYNCHRONIZATION
    # ========================================================================
    
    def adjust_time(self, timer_id, delta):
        """
        Adjust timer time by delta
        
        Args:
            timer_id: Timer to adjust
            delta: Milliseconds to add (positive) or subtract (negative)
        
        Returns:
            bool: Success status
        """
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'adjust_time',
            {
                'timer_id': timer_id,
                'delta': delta
            }
        )
        
        if success:
            current_app.logger.info(
                f"⏱️  Adjusted timer {timer_id} by {delta}ms"
            )
        
        return success
    
    def set_elapsed_time(self, timer_id, elapsed_time):
        """
        Set specific elapsed time
        
        Args:
            timer_id: Timer to update
            elapsed_time: Target elapsed time in milliseconds
        
        Returns:
            bool: Success status
        """
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'set_elapsed_time',
            {
                'timer_id': timer_id,
                'elapsed_time': elapsed_time
            }
        )
        
        if success:
            current_app.logger.info(
                f"⏱️  Set timer {timer_id} to {elapsed_time}ms"
            )
        
        return success
    
    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================
    
    def start_multiple(self, timer_ids):
        """
        Start multiple timers simultaneously
        
        Args:
            timer_ids: List of timer IDs to start
        
        Returns:
            bool: Success status
        """
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'start_multiple',
            {'timer_ids': timer_ids}
        )
        
        if success:
            with self.lock:
                for timer_id in timer_ids:
                    if timer_id in self.timers:
                        self.timers[timer_id]['state'] = 'running'
            
            current_app.logger.info(
                f"▶️  Started {len(timer_ids)} timers simultaneously"
            )
        
        return success
    
    # ========================================================================
    # STATE MANAGEMENT
    # ========================================================================
    
    def get_timer_state(self, timer_id):
        """
        Get cached timer state
        
        Args:
            timer_id: Timer identifier
        
        Returns:
            dict: Timer state or None
        """
        with self.lock:
            return self.timers.get(timer_id)
    
    def get_all_timers(self):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id,
            'get_all_timers',
            {}
        )

        if success:
            current_app.logger.info(
                "Signal 'get_all_timers' sent to Timer Plugin"
            )
        else:
            current_app.logger.warning("Timer Plugin is offline - cannot fetch timers")

        return success
    
    def update_timer_state(self, timer_id, updates):
        """
        Update cached timer state (called from WebSocket handler)
        
        Args:
            timer_id: Timer to update
            updates: Dictionary of updates
        """
        with self.lock:
            if timer_id not in self.timers:
                self.timers[timer_id] = {'id': timer_id}
            
            self.timers[timer_id].update(updates)
    
    def clear_all_timers(self):
        """Clear all cached timers"""
        with self.lock:
            self.timers.clear()
        current_app.logger.info("🗑️  Cleared all timers from cache")
    
    # ========================================================================
    # HIGH-LEVEL BUSINESS LOGIC
    # ========================================================================
    
    def create_game_timer(self, game_id, duration_minutes=40):
        """
        Create a timer for a match
        
        Args:
            game_id: Match identifier
            duration_minutes: Match duration in minutes
        
        Returns:
            str: Timer ID
        """
        timer_id = f'match-{game_id}'
        
        self.create_timer(
            timer_id=timer_id,
            timer_type='independent',
            limit=duration_minutes * 60 * 1000,
            pause_at_limit=False,
            update_interval_ms=100,
            metadata={
                'game_id': game_id,
                'type': 'match',
                'duration_minutes': duration_minutes
            }
        )
        
        return timer_id
    
    def create_penalty_timer(self, game_timer_id, player_info, 
                           duration_minutes=2):
        """
        Create a dependent timer for a penalty
        
        Args:
            game_timer_id: Parent match timer ID
            player_info: Dictionary with player details
            duration_minutes: Penalty duration in minutes
        
        Returns:
            str: Timer ID
        """
        timer_id = f'penalty-{player_info.get("number", "unknown")}-{datetime.now().timestamp()}'
        
        self.create_timer(
            timer_id=timer_id,
            timer_type='dependent',
            parent_id=game_timer_id,
            limit=duration_minutes * 60 * 1000,
            pause_at_limit=True,
            update_interval_ms=1000,
            metadata={
                **player_info,
                'type': 'penalty',
                'duration_minutes': duration_minutes
            }
        )
        
        return timer_id
    
    def create_rafting_timer(self, team_name, start_number):
        """
        Create independent timer for rafting team
        
        Args:
            team_name: Team name
            start_number: Start order number
        
        Returns:
            str: Timer ID
        """
        timer_id = f'rafting-{start_number}'
        
        self.create_timer(
            timer_id=timer_id,
            timer_type='independent',
            update_interval_ms=10,  # 10ms precision for rafting
            metadata={
                'team': team_name,
                'start_number': start_number,
                'type': 'rafting'
            }
        )
        
        return timer_id
    
    def create_parallel_skiing_timers(self, skier_blue, skier_red):
        """
        Create two parallel timers for skiing
        
        Args:
            skier_blue: Blue lane skier info
            skier_red: Red lane skier info
        
        Returns:
            tuple: (blue_timer_id, red_timer_id)
        """
        blue_id = f'ski-blue-{datetime.now().timestamp()}'
        red_id = f'ski-red-{datetime.now().timestamp()}'
        
        # Create both timers
        self.create_timer(
            timer_id=blue_id,
            timer_type='independent',
            update_interval_ms=10,
            metadata={**skier_blue, 'lane': 'blue', 'type': 'skiing'}
        )
        
        self.create_timer(
            timer_id=red_id,
            timer_type='independent',
            update_interval_ms=10,
            metadata={**skier_red, 'lane': 'red', 'type': 'skiing'}
        )
        
        return blue_id, red_id
    
    # ========================================================================
    # WEBSOCKET MESSAGE HANDLERS
    # ========================================================================
    
    def on_timer_updated(self, msg):
        """
        Handle timer_updated message from Timer Plugin
        
        Args:
            msg: Update payload
        """
        msg_type = msg.get('type')
        payload = msg.get('payload')
        timer_id = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time', 0)
        state = payload.get('state', 'unknown')
        limit = payload.get('limit', 0)
        
        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time,
            'state': state,
            'limit': limit,
            'last_update': datetime.now().isoformat()
        })
        
        # Emit to frontend via SocketIO
        self._emit_to_ui(msg_type, {
            'timer_id': timer_id,
            'elapsed_time': elapsed_time,
            'state': state,
            'limit': limit,
        })

    def on_timer_started(self, msg):
        """
        Handle timer_started message from Timer Plugin

        Args:
            msg: Update payload
        """
        msg_type = msg.get('type')
        payload = msg.get('payload')
        timer_id = payload.get('timer_id')
        state = payload.get('state', 'unknown')
        limit = payload.get('limit', 0)
        elapsed_time = 0
        if payload.get('elapsed_time') and payload.get('elapsed_time').isDigit():
            elapsed_time = payload.get('elapsed_time')
        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time,
            'state': state,
            'limit': limit,
            'last_update': datetime.now().isoformat()
        })

        # Emit to frontend via SocketIO
        self._emit_to_ui(msg_type, {
            'timer_id': timer_id,
            'elapsed_time': elapsed_time,
            'limit': limit,
            'state': state
        })

    def on_timer_paused(self, msg):
        """
        Handle timer_paused message from Timer Plugin

        Args:
            msg: Update payload
        """
        msg_type = msg.get('type')
        payload = msg.get('payload')
        timer_id = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time')
        state = payload.get('state', 'unknown')
        limit = payload.get('limit', 0)

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time,
            'state': state,
            'limit': limit,
            'last_update': datetime.now().isoformat()
        })

        # Emit to frontend via SocketIO
        self._emit_to_ui(msg_type, {
            'timer_id': timer_id,
            'elapsed_time': elapsed_time,
            'limit': limit,
            'state': state
        })

    def on_timer_reset(self, msg):
        """
        Handle timer_paused message from Timer Plugin

        Args:
            msg: Update payload
        """
        msg_type = msg.get('type')
        payload = msg.get('payload')
        timer_id = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time')
        state = payload.get('state', 'unknown')
        limit = payload.get('limit', 0)

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time,
            'state': state,
            'limit': limit,
            'last_update': datetime.now().isoformat()
        })

        # Emit to frontend via SocketIO
        self._emit_to_ui(msg_type, {
            'timer_id': timer_id,
            'elapsed_time': elapsed_time,
            'limit': limit,
            'state': state
        })

    def on_timer_adjusted(self, msg):
        """
        Handle timer_updated message from Timer Plugin

        Args:
            msg: Update payload
        """
        msg_type = msg.get('type')
        payload = msg.get('payload')
        timer_id = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time', 0)
        state = payload.get('state', 'idle')
        limit = payload.get('limit', 0)

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time,
            'state': state,
            'limit': limit,
            'last_update': datetime.now().isoformat()
        })

        # Emit to frontend via SocketIO
        self._emit_to_ui(msg_type, {
            'timer_id': timer_id,
            'elapsed_time': elapsed_time,
            'limit': limit,
            'state': state
        })

    def on_timer_event(self, data):
        """
        Handle timer_event message from Timer Plugin
        
        Args:
            data: Event payload
        """
        timer_id = data.get('timer_id')
        event = data.get('event')
        elapsed_time = data.get('elapsed_time', 0)
        
        current_app.logger.info(
            f"⏱️  Timer event: {timer_id} - {event} ({elapsed_time}ms)"
        )
        
        # Update state based on event
        state_map = {
            'limit_reached': 'limit_reached',
            'paused': 'paused',
            'resumed': 'running',
            'stopped': 'stopped',
            'running': 'running'
        }

        if event in state_map:
            self.update_timer_state(timer_id, {
                'state': state_map[event],
                'elapsed_time': elapsed_time
            })
        
        # Emit to frontend
        self._emit_to_ui('timer_event', {
            'timer_id': timer_id,
            'event': event,
            'elapsed_time': elapsed_time
        })

    def on_timer_created(self, msg):
        """
        Handle timer_updated message from Timer Plugin

        Args:
            msg: Update payload
        """
        msg_type = msg.get('type')
        payload = msg.get('payload')
        timer_id = payload.get('timer_id')
        initial_time = payload.get('initial_time')
        limit = payload.get('limit', 0)
        state = payload.get('state', 'idle')

        print(f'on_timer_created msg: {msg}')

        self.update_timer_state(timer_id, {
            'initial_time': initial_time,
            'state': state,
            'limit': limit,
            'last_update': datetime.now().isoformat()
        })

        game_timers = Settings.get_current_timers()
        if timer_id.startswith('penalty'):
            game_timer_id = game_timers['main']['timer_id']
            if timer_id.startswith('penalty_home') and len(game_timers['penalties']['home']) <= 2:
                msg_type = 'home_penalty_timer_created'
                team = 'home'
            elif timer_id.startswith('penalty_away') and len(game_timers['penalties']['away']) <= 2:
                msg_type = 'away_penalty_timer_created'
                team = 'away'
            else:
                self._emit_to_ui('flash_msg', {
                    'type': 'warning', 
                    'text': 'Błąd dodawania kary'
                })
                return

            timer_type = "dependent"
            team_name = payload.get('team_name')
            # Sync initial state with main timer state
            main_timer = game_timers.get('main', {})
            main_state = main_timer.get('state', 'idle') if main_timer else 'idle'
            if main_state == 'limit_reached':
                penalty_state = 'paused'
            else:
                penalty_state = main_state
            # Add to Settings.current_timers
            penalty_data = {
                "timer_id": timer_id,
                "timer_type": timer_type,
                "parent_id": game_timer_id,
                "initial_time": 0,
                "elapsed_time": 0,
                "limit": limit,
                "state": penalty_state,
                "metadata": {
                    "team": team,
                    "team_name": team_name,
                    "timer_class": "penalty",
                    "duration_minutes": int(limit/60000)
                }
            }
            Settings.add_penalty_timer(team, penalty_data)

            # Auto-start penalty timer if main timer is running
            if main_state == 'running':
                self.start_timer(timer_id)

            updated_timers = Settings.get_current_timers()
            home_penalties = updated_timers['penalties']['home']
            away_penalties = updated_timers['penalties']['away']
            penalties = {'home': home_penalties, 'away': away_penalties}

            self._emit_to_ui('reload_penalty_timers', {
                'penalties': penalties
            })

            
        else:
            timer_data = {
                "timer_id": timer_id,
                "timer_type": "independent",
                "initial_time": initial_time,
                "limit": limit,
                "pause_at_limit": True,
                "state": "idle",
                "metadata": {
                    "description": "1. połowa",
                    "period": 1,
                    "timer_class": "main"
                }
            }
            Settings.update_main_timer(timer_data)
            
            # Emit to frontend via SocketIO
            self._emit_to_ui(msg_type, {
                'timer_id': timer_id,
                'elapsed_time': initial_time,
                'initial_time': initial_time,
                'state': state,
                'limit': limit,
                'game_timers': game_timers
            })
    
    def on_timer_plugin_online(self):
        """Handle Timer Plugin coming online"""
        current_app.logger.info("✅ Timer Plugin is online")

        # Optionally: Re-create timers if needed
        # Or request current state

    def on_timer_plugin_offline(self):
        """Handle Timer Plugin going offline"""
        current_app.logger.warning("⚠️  Timer Plugin is offline")

        # Mark all timers as disconnected
        with self.lock:
            for timer_id in self.timers:
                self.timers[timer_id]['state'] = 'disconnected'

    def on_all_timers(self, msg):
        """
        Handle 'all_timers' response from timer-plugin
        
        This is called when timer-plugin sends list of all timers
        Used for recovery after crash/restart
        """
        msg_type = msg.get('type')
        payload = msg.get('payload')
        count = payload.get('count')
        timers = payload.get('timers', [])
        
        current_app.logger.info(f"📥 Received all timers from plugin: {count} timer(s)")
        
        # Log timers for debugging
        for timer in timers:
            timer_id = timer.get('timer_id')
            state = timer.get('state')
            current_app.logger.debug(f"  - {timer_id}: {state}")
        
        # Emit to frontend via SocketIO with specific event name
        # This event will be caught by timer-recovery.js
        self._emit_to_ui('timer_plugin_all_timers', {
            'count': count,
            'timers': timers
        })
        
        current_app.logger.info(f"📤 Sent all timers to UI")

    def on_limit_reached(self, msg):
        from app.models.settings import Settings
        
        msg_type = msg.get('type')
        payload = msg.get('payload')
        timer_id = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time')
        state = payload.get('state')
        pause_at_limit = payload.get('pause_at_limit')
        
        # Update timer state in Settings
        current_timers = Settings.get_current_timers()
        main_timer = current_timers.get("main")
        
        if main_timer and main_timer.get("timer_id") == timer_id:
            # Main timer reached limit
            main_timer["state"] = state
            main_timer["elapsed_time"] = elapsed_time
            Settings.update_main_timer(main_timer)

            # Pause all penalty timers that have not reached their limit yet
            _penalties = current_timers.get("penalties", {"home": [], "away": []})
            penalties = _penalties['home'] + _penalties['away']
            for penalty in penalties:
                if penalty.get("state") != "limit_reached":
                    penalty_id = penalty.get("timer_id")
                    if penalty_id:
                        self.pause_timer(penalty_id)
                        penalty_state = self.get_timer_state(penalty_id)
                        penalty["state"] = "paused"
                        penalty["elapsed_time"] = (
                            penalty_state.get("elapsed_time", penalty.get("elapsed_time", 0))
                            if penalty_state else penalty.get("elapsed_time", 0)
                        )
                        Settings.update_penalty_timer(penalty_id, penalty)

            self._emit_to_ui('reload_penalty_timers', {
                'penalties': Settings.get_current_timers().get("penalties", {"home": [], "away": []})
            })
        else:
            # Penalty timer reached limit
            _penalties = current_timers.get("penalties", {"home": [], "away": []})
            penalties = _penalties['home'] + _penalties['away']
            for penalty in penalties:
                if penalty.get("timer_id") == timer_id:
                    penalty["state"] = state
                    penalty["elapsed_time"] = elapsed_time
                    Settings.update_penalty_timer(timer_id, penalty)
                    break

        if pause_at_limit:
            self._emit_to_ui(msg_type, {
                'timer_id': timer_id,
                'elapsed_time': elapsed_time,
                'state': state
            })

    
    def _emit_to_ui(self, msg_type, data):
        """Emit event to UI clients via SocketIO"""
        try:
            from app.extensions import socketio
            # socketio.emit(event, data, broadcast=True)
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f"Failed to emit to UI: {e}")