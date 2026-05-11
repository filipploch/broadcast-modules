"""Timer Manager - Manages timer plugin communication and state"""
import threading
from datetime import datetime

from flask import current_app

from core.extensions import db

def _get_gametimer():
    from core.models.base_game_timer import get_game_timer_model
    return get_game_timer_model()



class TimerManager:
    """Manages communication with Timer Plugin and caches timer states."""

    def __init__(self, hub_client):
        self.hub_client = hub_client
        self.timer_plugin_id = 'timer-plugin'
        # Lekki in-memory cache: {plugin_timer_id: {...}}
        # Używany tylko do odczytów między tickami — źródłem prawdy jest DB.
        self.timers = {}
        self.lock = threading.Lock()
        current_app.logger.info('TimerManager initialized')

    # =========================================================================
    # TIMER LIFECYCLE — komunikacja z pluginem
    # =========================================================================

    def create_timer(self, timer_id, timer_type='independent', **kwargs):
        payload = {'timer_id': timer_id, 'timer_type': timer_type, **kwargs}
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'create_timer', payload
        )
        if success:
            with self.lock:
                self.timers[timer_id] = {
                    'timer_id':     timer_id,
                    'timer_type':   timer_type,
                    'state':        'idle',
                    'initial_time': kwargs.get('initial_time'),
                    'elapsed_time': 0,
                    'limit':        kwargs.get('limit'),
                    'parent_id':    kwargs.get('parent_id'),
                    'metadata':     kwargs.get('metadata', {}),
                }
            current_app.logger.info(f'✅ Created timer: {timer_id} ({timer_type})')
        else:
            current_app.logger.error(f'❌ Failed to create timer: {timer_id}')
        return success

    def ensure_timer(self, timer_id, timer_type='independent', **kwargs):
        """Idempotent create-or-reuse: sends ensure_timer to plugin.

        The plugin creates the timer only if it does not already exist
        in its memory. The response (timer_ensured) is handled by on_timer_ensured().
        """
        payload = {'timer_id': timer_id, 'timer_type': timer_type, **kwargs}
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'ensure_timer', payload
        )
        if success:
            with self.lock:
                if timer_id not in self.timers:
                    self.timers[timer_id] = {
                        'timer_id':     timer_id,
                        'timer_type':   timer_type,
                        'state':        'idle',
                        'initial_time': kwargs.get('initial_time'),
                        'elapsed_time': 0,
                        'limit':        kwargs.get('limit'),
                        'parent_id':    kwargs.get('parent_id'),
                        'metadata':     kwargs.get('metadata', {}),
                    }
            current_app.logger.info(f'✅ Ensured timer: {timer_id} ({timer_type})')
        else:
            current_app.logger.error(f'❌ Failed to ensure timer: {timer_id}')
        return success

    def start_timer(self, timer_id):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'start_timer', {'timer_id': timer_id}
        )
        if success:
            with self.lock:
                if timer_id in self.timers:
                    self.timers[timer_id]['state'] = 'running'
            current_app.logger.info(f'▶️  Started timer: {timer_id}')
        return success

    def pause_timer(self, timer_id):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'pause_timer', {'timer_id': timer_id}
        )
        if success:
            with self.lock:
                if timer_id in self.timers:
                    self.timers[timer_id]['state'] = 'paused'
            current_app.logger.info(f'⏸️  Paused timer: {timer_id}')
        return success

    def resume_timer(self, timer_id):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'resume_timer', {'timer_id': timer_id}
        )
        if success:
            with self.lock:
                if timer_id in self.timers:
                    self.timers[timer_id]['state'] = 'running'
            current_app.logger.info(f'▶️  Resumed timer: {timer_id}')
        return success

    def reset_timer(self, timer_id):
        return self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'reset_timer', {'timer_id': timer_id}
        )

    def remove_timer(self, timer_id):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'remove_timer', {'timer_id': timer_id}
        )
        if success:
            with self.lock:
                self.timers.pop(timer_id, None)
            current_app.logger.info(f'🗑️  Removed timer: {timer_id}')
        return success

    # =========================================================================
    # TIME SYNCHRONIZATION
    # =========================================================================

    def adjust_time(self, timer_id, delta):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'adjust_time',
            {'timer_id': timer_id, 'delta': delta}
        )
        if success:
            current_app.logger.info(f'⏱️  Adjusted timer {timer_id} by {delta}ms')
        return success

    def set_elapsed_time(self, timer_id, elapsed_time):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'set_elapsed_time',
            {'timer_id': timer_id, 'elapsed_time': elapsed_time}
        )
        if success:
            current_app.logger.info(f'⏱️  Set timer {timer_id} to {elapsed_time}ms')
        return success

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    def start_multiple(self, timer_ids):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'start_multiple', {'timer_ids': timer_ids}
        )
        if success:
            with self.lock:
                for tid in timer_ids:
                    if tid in self.timers:
                        self.timers[tid]['state'] = 'running'
            current_app.logger.info(
                f'▶️  Started {len(timer_ids)} timers simultaneously'
            )
        return success

    # =========================================================================
    # STATE — in-memory cache
    # =========================================================================

    def get_timer_state(self, timer_id):
        with self.lock:
            return self.timers.get(timer_id)

    def get_all_timers(self):
        success = self.hub_client.send_to_plugin(
            self.timer_plugin_id, 'get_all_timers', {}
        )
        if not success:
            current_app.logger.warning('Timer Plugin is offline - cannot fetch timers')
        return success

    def update_timer_state(self, timer_id, updates):
        with self.lock:
            if timer_id not in self.timers:
                self.timers[timer_id] = {'id': timer_id}
            self.timers[timer_id].update(updates)

    def clear_all_timers(self):
        with self.lock:
            self.timers.clear()
        current_app.logger.info('🗑️  Cleared all timers from cache')

    # =========================================================================
    # HIGH-LEVEL BUSINESS LOGIC
    # =========================================================================

    def create_game_timer(self, game_id, duration_minutes=40, pause_at_limit=False):
        timer_id = f'match-{game_id}'
        self.create_timer(
            timer_id=timer_id,
            timer_type='independent',
            limit=duration_minutes * 60 * 1000,
            pause_at_limit=False,
            update_interval_ms=100,
            metadata={'game_id': game_id, 'type': 'match',
                      'duration_minutes': duration_minutes,
                      'pause_at_limit': pause_at_limit},
        )
        return timer_id

    def create_penalty_timer(self, game_timer_id, player_info, duration_minutes=2):
        timer_id = (
            f'penalty-{player_info.get("number", "unknown")}'
            f'-{datetime.now().timestamp()}'
        )
        self.create_timer(
            timer_id=timer_id,
            timer_type='dependent',
            parent_id=game_timer_id,
            limit=duration_minutes * 60 * 1000,
            pause_at_limit=True,
            update_interval_ms=1000,
            metadata={**player_info, 'type': 'penalty',
                      'duration_minutes': duration_minutes},
        )
        return timer_id

    def create_rafting_timer(self, team_name, start_number):
        timer_id = f'rafting-{start_number}'
        self.create_timer(
            timer_id=timer_id,
            timer_type='independent',
            update_interval_ms=10,
            metadata={'team': team_name, 'start_number': start_number,
                      'type': 'rafting'},
        )
        return timer_id

    def create_parallel_skiing_timers(self, skier_blue, skier_red):
        blue_id = f'ski-blue-{datetime.now().timestamp()}'
        red_id  = f'ski-red-{datetime.now().timestamp()}'
        self.create_timer(timer_id=blue_id, timer_type='independent',
                          update_interval_ms=10,
                          metadata={**skier_blue, 'lane': 'blue', 'type': 'skiing'})
        self.create_timer(timer_id=red_id, timer_type='independent',
                          update_interval_ms=10,
                          metadata={**skier_red, 'lane': 'red', 'type': 'skiing'})
        return blue_id, red_id

    # =========================================================================
    # DB HELPERS
    # =========================================================================

    @staticmethod
    def get_db_timer(plugin_timer_id: str):
        return _get_gametimer().query.filter_by(plugin_timer_id=plugin_timer_id).first()

    @staticmethod
    def get_active_main_timer(period_id: int):
        GameTimer = _get_gametimer()
        return GameTimer.query.filter(
            GameTimer.period_id == period_id,
            GameTimer.timer_type == GameTimer.TYPE_MAIN,
            GameTimer.state.in_([
                GameTimer.STATE_IDLE,
                GameTimer.STATE_RUNNING,
                GameTimer.STATE_PAUSED,
            ]),
        ).first()

    @staticmethod
    def get_active_penalties(period_id: int):
        GameTimer = _get_gametimer()
        return GameTimer.query.filter(
            GameTimer.period_id == period_id,
            GameTimer.timer_type == GameTimer.TYPE_PENALTY,
            GameTimer.state.in_([
                GameTimer.STATE_IDLE,
                GameTimer.STATE_RUNNING,
                GameTimer.STATE_PAUSED,
            ]),
        ).order_by(GameTimer.created_at).all()

    @staticmethod
    def get_active_penalties_by_team(game_id: int, team: str):
        GameTimer = _get_gametimer()
        return GameTimer.query.filter(
            GameTimer.game_id == game_id,
            GameTimer.timer_type == GameTimer.TYPE_PENALTY,
            GameTimer.team == team,
            GameTimer.state.in_([
                GameTimer.STATE_IDLE,
                GameTimer.STATE_RUNNING,
                GameTimer.STATE_PAUSED,
            ]),
        ).order_by(GameTimer.created_at).all()

    # =========================================================================
    # WEBSOCKET MESSAGE HANDLERS
    # =========================================================================

    def on_timer_updated(self, msg):
        payload      = msg.get('payload', {})
        print('on_timer_updated', payload)
        timer_id     = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time', 0)
        state        = payload.get('state', 'unknown')
        limit        = payload.get('limit', 0)
        initial_time = payload.get('initial_time', 0)

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time, 'state': state, 'initial_time': initial_time,
            'limit': limit, 'last_update': datetime.now().isoformat(),
        })
        self._sync_db_timer(timer_id, elapsed_time, state)
        self._emit_to_ui(msg.get('type'), {
            'timer_id': timer_id, 'elapsed_time': elapsed_time,
            'state': state, 'limit': limit, 'initial_time': initial_time,
        })

    def on_timer_started(self, msg):
        payload      = msg.get('payload', {})
        timer_id     = payload.get('timer_id')
        state        = payload.get('state', 'unknown')
        limit        = payload.get('limit', 0)
        elapsed_time = payload.get('elapsed_time') or 0
        initial_time = payload.get('initial_time', 0)

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time, 'state': state, 'initial_time': initial_time,
            'limit': limit, 'last_update': datetime.now().isoformat(),
        })
        self._sync_db_timer(timer_id, elapsed_time, state)
        self._emit_to_ui(msg.get('type'), {
            'timer_id': timer_id, 'elapsed_time': elapsed_time,
            'limit': limit, 'state': state, 'initial_time': initial_time,
        })

    def on_timer_paused(self, msg):
        payload      = msg.get('payload', {})
        timer_id     = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time', 0)
        state        = payload.get('state', 'unknown')
        limit        = payload.get('limit', 0)
        initial_time = payload.get('initial_time', 0)

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time, 'state': state, 'initial_time': initial_time,
            'limit': limit, 'last_update': datetime.now().isoformat(),
        })
        self._sync_db_timer(timer_id, elapsed_time, state)
        self._emit_to_ui(msg.get('type'), {
            'timer_id': timer_id, 'elapsed_time': elapsed_time,
            'limit': limit, 'state': state, 'initial_time': initial_time,
        })

    def on_timer_reset(self, msg):
        payload      = msg.get('payload', {})
        timer_id     = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time', 0)
        state        = payload.get('state', 'unknown')
        limit        = payload.get('limit', 0)
        initial_time = payload.get('initial_time', 0)

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time, 'state': state, 'initial_time': initial_time,
            'limit': limit, 'last_update': datetime.now().isoformat(),
        })
        self._sync_db_timer(timer_id, elapsed_time, state)
        self._emit_to_ui(msg.get('type'), {
            'timer_id': timer_id, 'elapsed_time': elapsed_time,
            'limit': limit, 'state': state, 'initial_time': initial_time,
        })

    def on_timer_adjusted(self, msg):
        payload      = msg.get('payload', {})
        timer_id     = payload.get('timer_id')
        elapsed_time = payload.get('elapsed_time', 0)
        state        = payload.get('state', 'idle')
        limit        = payload.get('limit', 0)
        initial_time = payload.get('initial_time', 0)

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time, 'state': state, 'initial_time': initial_time,
            'limit': limit, 'last_update': datetime.now().isoformat(),
        })
        self._sync_db_timer(timer_id, elapsed_time, state)
        self._emit_to_ui(msg.get('type'), {
            'timer_id': timer_id, 'elapsed_time': elapsed_time,
            'limit': limit, 'state': state, 'initial_time': initial_time,
        })

    def on_timer_event(self, data):
        timer_id     = data.get('timer_id')
        event        = data.get('event')
        elapsed_time = data.get('elapsed_time', 0)

        current_app.logger.info(
            f'⏱️  Timer event: {timer_id} - {event} ({elapsed_time}ms)'
        )

        state_map = {
            'limit_reached': 'limit_reached',
            'paused':        'paused',
            'resumed':       'running',
            'stopped':       'stopped',
            'running':       'running',
        }
        if event in state_map:
            new_state = state_map[event]
            self.update_timer_state(timer_id, {
                'state': new_state, 'elapsed_time': elapsed_time,
            })
            self._sync_db_timer(timer_id, elapsed_time, new_state)

        self._emit_to_ui('timer_event', {
            'timer_id': timer_id, 'event': event, 'elapsed_time': elapsed_time,
        })

    def on_timer_created(self, msg):
        """
        Potwierdzenie utworzenia timera z pluginu.
        Zapisuje rekord GameTimer w DB i powiadamia UI.
        """
        from core.models.base_game_timer import get_game_timer_model
        GameTimer = get_game_timer_model()
        payload      = msg.get('payload', {})
        timer_id     = payload.get('timer_id')
        initial_time = payload.get('initial_time', 0) or 0
        limit        = payload.get('limit', 0) or 0
        state        = payload.get('state', 'idle')
        metadata     = payload.get('metadata', {}) or {}

        self.update_timer_state(timer_id, {
            'elapsed_time': 0,
            'initial_time': initial_time,
            'state': state,
            'limit': limit,
            'last_update': datetime.now().isoformat()
        })

        is_penalty = (timer_id.startswith('penalty_home') or
                      timer_id.startswith('penalty_away'))

        if is_penalty:
            self._handle_penalty_timer_created(timer_id, limit, state, metadata)
        else:
            self._handle_main_timer_created(timer_id, initial_time, limit,
                                            state, metadata)

    def _handle_main_timer_created(self, timer_id, initial_time, limit,
                                   state, metadata):
        from core.models.base_game_timer import get_game_timer_model
        GameTimer = get_game_timer_model()
        from core.models.base_settings import get_settings_model
        Settings = get_settings_model()
        settings  = Settings.get_settings()
        game_id   = settings.current_game_id
        period_id = settings.current_period_id

        # Zapisz/zaktualizuj rekord w game_timers
        gt = _get_gametimer().query.filter_by(plugin_timer_id=timer_id).first()
        if gt is None:
            gt = _get_gametimer()(
                game_id=game_id, period_id=period_id,
                timer_type=GameTimer.TYPE_MAIN,
                plugin_timer_id=timer_id,
                elapsed_time_ms=0, limit_ms=limit,
                state=GameTimer.STATE_IDLE,
            )
            db.session.add(gt)
        else:
            gt.elapsed_time_ms = 0
            gt.limit_ms        = limit
            gt.state           = GameTimer.STATE_IDLE
            gt.period_id       = period_id  # odśwież period_id na wypadek zmiany
            gt.updated_at      = datetime.utcnow()

        db.session.commit()

        # Zsynchronizuj settings.current_timers — to jest źródło prawdy dla UI/timer-plugin
        # przy starcie okresu period_manager.start_period() już woła Settings.update_main_timer(),
        # ale robimy to tu ponownie żeby zagwarantować spójność po asynchronicznym potwierdzeniu
        # z pluginu (on_timer_created może nadejść z opóźnieniem po zmianie period_id w settings).
        pause_at_limit = metadata.get('pause_at_limit', True)
        main_timer_data = {
            'timer_id':      timer_id,
            'timer_type':    'independent',
            'initial_time':  initial_time,
            'limit':         limit,
            'pause_at_limit': pause_at_limit,
            'state':         GameTimer.STATE_IDLE,
            'elapsed_time':  0,
            'metadata':      metadata,
        }
        Settings.update_main_timer(main_timer_data)

        self._emit_to_ui('timer_created', {
            'timer_id': timer_id, 'elapsed_time': 0,
            'initial_time': initial_time, 'state': state, 'limit': limit,
        })

    def _handle_penalty_timer_created(self, timer_id, limit, state, metadata):
        from core.models.base_game_timer import get_game_timer_model
        GameTimer = get_game_timer_model()
        from core.models.base_settings import get_settings_model
        Settings = get_settings_model()
        settings  = Settings.get_settings()
        game_id   = settings.current_game_id
        period_id = settings.current_period_id

        team         = 'home' if timer_id.startswith('penalty_home') else 'away'
        main_gt      = self.get_active_main_timer(period_id)
        main_state   = main_gt.state if main_gt else GameTimer.STATE_IDLE
        start_offset = main_gt.elapsed_time_ms if main_gt else 0

        penalty_state = (
            GameTimer.STATE_PAUSED
            if main_state == GameTimer.STATE_LIMIT_REACHED
            else main_state
        )

        gt = _get_gametimer()(
            game_id=game_id, period_id=period_id,
            timer_type=GameTimer.TYPE_PENALTY,
            team=team, plugin_timer_id=timer_id,
            elapsed_time_ms=0, limit_ms=limit,
            state=penalty_state, start_offset_ms=start_offset,
        )
        db.session.add(gt)
        db.session.commit()

        if main_state == GameTimer.STATE_RUNNING:
            self.start_timer(timer_id)

        penalties = self._get_penalties_dict(game_id)
        self._emit_to_ui('reload_penalty_timers', {'penalties': penalties})
        self._broadcast_penalty_state(game_id)

    def on_timer_ensured(self, msg):
        """
        Response from plugin after ensure_timer.
        If created=True the timer is new — run full DB setup.
        If created=False the timer already existed — sync state to UI.
        """
        payload      = msg.get('payload', {})
        timer_id     = payload.get('timer_id')
        created      = payload.get('created', False)
        initial_time = payload.get('initial_time', 0) or 0
        limit        = payload.get('limit', 0) or 0
        state        = payload.get('state', 'idle')
        elapsed_time = payload.get('elapsed_time', 0) or 0
        metadata     = payload.get('metadata', {}) or {}

        self.update_timer_state(timer_id, {
            'elapsed_time': elapsed_time,
            'initial_time': initial_time,
            'state':        state,
            'limit':        limit,
            'last_update':  datetime.now().isoformat(),
        })

        if created:
            is_penalty = (timer_id.startswith('penalty_home') or
                          timer_id.startswith('penalty_away'))
            if is_penalty:
                self._handle_penalty_timer_created(timer_id, limit, state, metadata)
            else:
                self._handle_main_timer_created(timer_id, initial_time, limit,
                                                state, metadata)
        else:
            self._emit_to_ui('timer_ensured', {
                'timer_id':     timer_id,
                'elapsed_time': elapsed_time,
                'initial_time': initial_time,
                'state':        state,
                'limit':        limit,
            })

    def on_limit_reached(self, msg):
        from core.models.base_game_timer import get_game_timer_model
        GameTimer = get_game_timer_model()
        payload        = msg.get('payload', {})
        timer_id       = payload.get('timer_id')
        elapsed_time   = payload.get('elapsed_time', 0)
        state          = payload.get('state', GameTimer.STATE_LIMIT_REACHED)
        pause_at_limit = payload.get('pause_at_limit', True)

        gt = self.get_db_timer(timer_id)
        if gt is None:
            current_app.logger.warning(
                f'on_limit_reached: nieznany timer {timer_id}'
            )
            return

        gt.sync_from_plugin(elapsed_time, state)

        if gt.timer_type == GameTimer.TYPE_MAIN:
            # Pauzuj wszystkie aktywne kary w jednej transakcji
            for pen in self.get_active_penalties(gt.game_id):
                if pen.state != GameTimer.STATE_LIMIT_REACHED:
                    pen.sync_from_plugin(pen.elapsed_time_ms,
                                         GameTimer.STATE_PAUSED)
                    if pen.plugin_timer_id:
                        self.pause_timer(pen.plugin_timer_id)

            db.session.commit()
            penalties = self._get_penalties_dict(gt.game_id)
            self._emit_to_ui('reload_penalty_timers', {'penalties': penalties})
            self._broadcast_penalty_state(gt.game_id)
        else:
            db.session.commit()

        if pause_at_limit:
            self._emit_to_ui(msg.get('type'), {
                'timer_id': timer_id, 'elapsed_time': elapsed_time,
                'state': state,
            })

    def on_timer_plugin_online(self):
        current_app.logger.info('✅ Timer Plugin is online')

    def on_timer_plugin_offline(self):
        current_app.logger.warning('⚠️  Timer Plugin is offline')
        with self.lock:
            for timer_id in self.timers:
                self.timers[timer_id]['state'] = 'disconnected'

    def on_all_timers(self, msg):
        payload = msg.get('payload', {})
        timers  = payload.get('timers', [])
        count   = payload.get('count', len(timers))
        current_app.logger.info(
            f'📥 Received all timers from plugin: {count} timer(s)'
        )
        self._emit_to_ui('timer_plugin_all_timers', {
            'count': count, 'timers': timers,
        })

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _sync_db_timer(self, plugin_timer_id: str,
                       elapsed_time_ms: int, state: str):
        try:
            gt = _get_gametimer().query.filter_by(
                plugin_timer_id=plugin_timer_id
            ).first()
            if gt is None:
                return
            gt.sync_from_plugin(elapsed_time_ms, state)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(
                f'_sync_db_timer({plugin_timer_id}): {e}'
            )

    @staticmethod
    def _get_penalties_dict(game_id: int) -> dict:
        from core.models.base_game_timer import get_game_timer_model
        GameTimer = get_game_timer_model()
        
        penalties = _get_gametimer().query.filter(
            GameTimer.game_id == game_id,
            GameTimer.timer_type == GameTimer.TYPE_PENALTY,
            GameTimer.state.in_([
                GameTimer.STATE_IDLE,
                GameTimer.STATE_RUNNING,
                GameTimer.STATE_PAUSED,
            ]),
        ).order_by(GameTimer.created_at).all()

        result = {'home': [], 'away': []}
        for p in penalties:
            result[p.team].append(p.to_dict())
        return result

    def _emit_to_ui(self, msg_type, data):
        try:
            from core.extensions import socketio
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f'Failed to emit to UI: {e}')

    def _broadcast_penalty_state(self, game_id: int):
        """
        Broadkastuje aktualny stan aktywnych kar do klasy 'overlay' przez hub.
        Wywoływać po każdej zmianie stanu kar (nowa kara, usunięcie, limit_reached).
        """
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if hub_client:
            hub_client.broadcast_to_class(
                'overlay',
                'penalty_state',
                self._get_penalties_dict(game_id),
            )