"""Hub Client - WebSocket communication with Hub - WITH BROADCAST CLASSES"""
import websocket
import json
import threading
import time
from datetime import datetime


class HubClient:
    """WebSocket client for Hub communication"""

    def __init__(self, hub_url, app=None):
        self.hub_url = hub_url
        self.app = app  # ⭐ Store Flask app instance
        self.ws = None
        self.module_id = None
        self.module_name = None
        self.connected = False
        self.message_handlers = []
        self._lock = threading.Lock()
        self.subscribe_classes = []
        self.required_plugins = []
        self._should_reconnect = True  # Kontrola reconnect
        self._reconnect_delay = 3  # Sekundy między próbami

    def connect(self):
        """Connect to Hub"""
        self._log("info", f"Connecting to Hub: {self.hub_url}")
        self._should_reconnect = True  # ✅ Włącz reconnect

        try:
            self.ws = websocket.WebSocketApp(
                self.hub_url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )

            # Start WebSocket in background thread
            ws_thread = threading.Thread(target=self._run_forever, daemon=True)
            ws_thread.start()

            # Wait for connection
            timeout = 5
            start_time = time.time()
            while not self.connected and time.time() - start_time < timeout:
                time.sleep(0.1)

            if not self.connected:
                raise Exception("Failed to connect to Hub")

            self._log("info", "Connected to Hub")

        except Exception as e:
            self._log("error", f"Failed to connect to Hub: {e}")
            raise

    def _run_forever(self):
        """Run WebSocket connection with auto-reconnect"""
        attempt = 0
        
        while self._should_reconnect:  # ✅ Zmieniono warunek
            try:
                if attempt > 0:
                    self._log("info", f"Reconnect attempt {attempt}...")
                
                self.ws.run_forever()
                
            except Exception as e:
                self._log("error", f"WebSocket error: {e}")

            # If disconnected and should reconnect
            if not self.connected and self._should_reconnect:
                attempt += 1
                self._log("info", f"Reconnecting to Hub in {self._reconnect_delay}s...")
                time.sleep(self._reconnect_delay)
                
                # ✅ Re-create WebSocket
                self.ws = websocket.WebSocketApp(
                    self.hub_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open
                )
            else:
                break
        
        self._log("info", "WebSocket thread stopped")

    def register_as_main_module(self, module_id, module_name, required_plugins=None, subscribe_classes=None):
        """
        Register as main module

        Args:
            module_id: Unique module identifier
            module_name: Human-readable module name
            required_plugins: List of required plugin IDs (optional)
            subscribe_classes: List of classes to subscribe to (optional)
        """
        self.module_id = module_id
        self.module_name = module_name

        # ✅ Zapisz parametry dla reconnect
        if required_plugins:
            self.required_plugins = required_plugins
        if subscribe_classes:
            self.subscribe_classes = subscribe_classes

        self._log("info", f"Registering as main module: {module_id}")

        # Get app_port from app config
        app_port = self._get_config('APP_PORT', 8081)

        # Resolve absolute DB path from SQLAlchemy URI
        import os
        db_path = ''
        try:
            db_uri = self._get_config('SQLALCHEMY_DATABASE_URI', '')
            db_filename = db_uri.replace('sqlite:///', '').replace('sqlite://', '')
            if self.app:
                db_path = os.path.join(self.app.instance_path, db_filename)
            else:
                db_path = db_filename
        except Exception:
            pass

        self.send({
            'from': module_id,
            'to': 'hub',
            'type': 'register',
            'payload': {
                'id': module_id,
                'name': module_name,
                'component_type': 'main_module',
                'host': 'localhost',
                'port': str(app_port),
                'type': 'local',
                'database_path': db_path
            }
        })

        # ✅ NEW: Subscribe to classes if provided
        if subscribe_classes:
            self.subscribe_classes = subscribe_classes
            # Subscribe will be sent in _on_open after connection confirmed

        # Declare required plugins if provided
        # if required_plugins:
        #     # Wait a bit for registration to complete
        #     time.sleep(0.1)
        #     self.declare_required_plugins(required_plugins)

    def declare_required_plugins(self, plugins):
        self.required_plugins = plugins
        """Declare required plugins to Hub"""
        self._log("info", f"Declaring {len(plugins)} required plugins")

        self.send({
            'from': self.module_id,
            'to': 'hub',
            'type': 'declare_required_plugins',
            'payload': {
                'owner_id': self.module_id,
                'plugins': plugins
            }
        })

    def send(self, message):
        """Send message to Hub"""
        if not self.connected:
            self._log("warning", "Cannot send - not connected to Hub")
            return False

        try:
            if 'timestamp' not in message:
                message['timestamp'] = datetime.utcnow().isoformat()

            with self._lock:
                self.ws.send(json.dumps(message))

            return True

        except Exception as e:
            self._log("error", f"Failed to send message: {e}")
            return False

    def broadcast(self, msg_type, payload):
        """Broadcast message to all plugins"""
        return self.send({
            'from': self.module_id,
            'to': 'broadcast',
            'type': msg_type,
            'payload': payload
        })

    # ✅ NEW: Broadcast to specific class
    def broadcast_to_class(self, class_name, msg_type, payload):
        """Broadcast message to specific class of modules"""
        return self.send({
            'from': self.module_id,
            'to': f'broadcast:{class_name}',
            'type': msg_type,
            'payload': payload
        })

    def send_to_plugin(self, plugin_id, msg_type, payload):
        """Send message to specific plugin"""
        return self.send({
            'from': self.module_id,
            'to': plugin_id,
            'type': msg_type,
            'payload': payload
        })

    # ✅ NEW: Subscribe to classes
    def subscribe_to_classes(self, classes):
        """
        Subscribe to broadcast classes

        Args:
            classes: List of class names to subscribe to
        """
        if not isinstance(classes, list):
            classes = [classes]

        self.subscribe_classes = classes

        self._log("info", f"Subscribing to classes: {', '.join(classes)}")

        return self.send({
            'from': self.module_id,
            'to': 'hub',
            'type': 'subscribe',
            'payload': {
                'class': classes
            }
        })

    # ✅ NEW: Unsubscribe from classes
    def unsubscribe(self, classes):
        """
        Unsubscribe from broadcast classes

        Args:
            classes: List of class names to unsubscribe from
        """
        if not isinstance(classes, list):
            classes = [classes]

        self._log("info", f"Unsubscribing from classes: {', '.join(classes)}")

        return self.send({
            'from': self.module_id,
            'to': 'hub',
            'type': 'unsubscribe',
            'payload': {
                'classes': classes
            }
        })

    def add_message_handler(self, handler):
        """Add message handler callback"""
        self.message_handlers.append(handler)

    def _on_message(self, ws, message):
        """Handle incoming message - RUNS IN WEBSOCKET THREAD"""
        try:
            msg = json.loads(message)
            # Log message (with app context)
            msg_type = msg.get('type', 'unknown')
            msg_from = msg.get('from', 'unknown')
            # self._log("debug", f"Received: {msg_type} from {msg_from}")

            # Handle message in app context
            if self.app:
                with self.app.app_context():
                    self._handle_message(msg)

                    # Call registered handlers
                    for handler in self.message_handlers:
                        try:
                            handler(msg)
                        except Exception as e:
                            self._log("error", f"Error in message handler: {e}", exc_info=True)
            else:
                # No app context available, handle without it
                self._handle_message(msg)

                for handler in self.message_handlers:
                    try:
                        handler(msg)
                    except Exception as e:
                        self._log("error", f"Error in message handler: {e}")

        except Exception as e:
            self._log("error", f"Error processing message: {e}", exc_info=True)

    def _handle_message(self, msg):
        """Handle specific message types"""
        msg_type = msg.get('type')
        msg_from = msg.get('from', '')
        payload = msg.get('payload', {})

        if msg_type == 'registered':
            self._log("info", "Registered with Hub")

            # ✅ NEW: Auto-subscribe to classes after registration
            # if self.subscribe_classes:
            #     self.subscribe_to_classes(self.subscribe_classes)

        # ✅ NEW: Handle subscription confirmation
        elif msg_type == 'subscribed':
            classes = payload.get('classes', [])
            self._log("info", f"✅ Subscribed to classes: {', '.join(classes)}")

        elif msg_type == 'plugin_status':
            # Hub sends this when any expected plugin connects or disconnects.
            plugin_id = payload.get('plugin_id')
            status    = payload.get('status')
            self._log("info", f"Plugin status: {plugin_id} → {status}")

            if status == 'connected':
                self._on_plugin_connected(plugin_id)

        elif msg_type == 'plugin_online':
            # Legacy alias — kept for backward compatibility with older hub builds.
            plugin_id = payload.get('plugin_id')
            self._log("info", f"Plugin online (legacy): {plugin_id}")
            self._on_plugin_connected(plugin_id)

        elif msg_type == 'plugin_offline':
            plugin_id = payload.get('plugin_id')
            self._log("warning", f"Plugin offline: {plugin_id}")
            if plugin_id and plugin_id.startswith('cam-head-'):
                from core.managers import get_servo_manager
                servo_manager = get_servo_manager()
                if servo_manager:
                    servo_manager.on_head_offline(plugin_id)

        elif msg_type == 'health_status':
            from core.managers import get_plugin_manager
            plugin_manager = get_plugin_manager()
            plugin_manager.on_plugins_state_received(msg)
            # print(f"health_status: {msg}")

        elif msg_from == 'stream-overlay':
            from core.managers.game_manager import GameManager
            game_manager = GameManager()
            if msg_type == 'request_game_data':
                game_manager.handle_request_game_data(msg)

        elif msg_from == 'recorder-plugin':
            from core.managers import get_recorder_manager
            recorder_manager = get_recorder_manager()
            if msg_type == 'recording_started':
                self._log("info", f"Recording started: camera={payload.get('camera_id')} file={payload.get('file_name')}")
                recorder_manager.on_recording_started(msg)
            elif msg_type == 'recording_stopped':
                self._log("info", f"Recording stopped: camera={payload.get('camera_id')}")
                recorder_manager.on_recording_stopped(msg)
            elif msg_type == 'recording_status_response':
                recorder_manager.on_recording_status_received(msg)
            elif msg_type == 'recording_command_response':
                recorder_manager.on_recording_command_response(msg)

        if msg_from == 'obs-ws-plugin':
            from core.managers import get_obs_ws_manager
            obs_ws_manager = get_obs_ws_manager()
            if msg_type == 'obs_status':
                obs_ws_manager.on_obs_status(msg)
            elif msg_type == 'obs_response':
                obs_ws_manager.on_obs_response(msg)
            elif msg_type == 'obs_event':
                obs_ws_manager.on_obs_event(msg)
            elif msg_type == 'obs_scene_map':
                obs_ws_manager.on_obs_scene_map(msg)
            elif msg_type == 'obs_error':
                self._log("error", f"OBS error: {msg}")
            else:
                self._log("warning", f"Unhandled OBS message type '{msg_type}'")



        if msg_from == 'timer-plugin':
            from core.managers import get_timer_manager
            tm = get_timer_manager()
            if msg_type == 'timer_updated':
                tm.on_timer_updated(msg)
            elif msg_type == 'timer_started':
                tm.on_timer_started(msg)
            elif msg_type == 'timer_paused':
                tm.on_timer_paused(msg)
            elif msg_type == 'timer_reset':
                tm.on_timer_reset(msg)
            elif msg_type == 'timer_adjusted':
                tm.on_timer_adjusted(msg)
            elif msg_type == 'timer_resumed':
                tm.on_timer_updated(msg)
            elif msg_type == 'timer_created':
                tm.on_timer_created(msg)
            elif msg_type == 'timer_ensured':
                tm.on_timer_ensured(msg)
            elif msg_type == 'limit_reached':
                tm.on_limit_reached(msg)
            elif msg_type == 'all_timers':
                tm.on_all_timers(msg)

        # Replay Plugin messages
        if msg_from == 'replay-plugin':
            from core.managers import get_sequence_manager, get_controller_manager
            seq_mgr = get_sequence_manager()
            controller_mgr = get_controller_manager()

            if msg_type == 'replay_done':
                if seq_mgr:
                    seq_mgr.notify_hub_message('replay_done')
                    self._log("info", f"[replay] replay_done — sekwencja powiadomiona")
                    seq_mgr.emit_to_ui('replay_done', payload)
                if controller_mgr:
                    controller_mgr.on_replay_done(payload)

            elif msg_type == 'replay_started':
                if seq_mgr:
                    seq_mgr.notify_hub_message('replay_started', payload)
                    seq_mgr.emit_to_ui('replay_started', payload)
                if controller_mgr:
                    controller_mgr.on_replay_started(payload)
                self._log("info", f"[replay] started: speed={payload.get('speed')}")

            elif msg_type == 'replay_paused':
                # ⭐ NOWE: po replay_pause od main-module → mpv pauza → ten sygnał
                if seq_mgr:
                    seq_mgr.emit_to_ui('replay_paused', payload)
                if controller_mgr:
                    controller_mgr.on_replay_paused(payload)

            elif msg_type == 'replay_resumed':
                # ⭐ NOWE: po replay_resume
                if seq_mgr:
                    seq_mgr.emit_to_ui('replay_resumed', payload)
                if controller_mgr:
                    controller_mgr.on_replay_resumed(payload)

            elif msg_type == 'replay_state':
                # Zachowane dla wstecznej kompatybilności (replay-plugin emituje
                # to obok replay_started)
                status = payload.get('status')
                if seq_mgr and status == 'playing':
                    seq_mgr.emit_to_ui('replay_started', payload)
                self._log("info", f"[replay] state: {status}")

            elif msg_type == 'replay_error':
                self._log("warning", f"[replay] error: {payload.get('error')}")

                # Controller Plugin messages
        if msg_from == 'controller-plugin':
            from core.managers import get_controller_manager
            controller_mgr = get_controller_manager()
            if controller_mgr:
                if msg_type == 'controller_button':
                    controller_mgr.on_controller_button(payload)
                elif msg_type == 'controller_wheel':
                    controller_mgr.on_controller_wheel(payload)
            else:
                self._log("warning",
                          f"[controller] message {msg_type} dropped — manager not initialized")

        if msg_from.startswith('cam-head-'):
            if msg_type == 'servo_status':
                from core.managers import get_servo_manager
                servo_manager = get_servo_manager()
                if servo_manager:
                    servo_manager.on_servo_status(msg)
            elif msg_type == 'gopro_status':
                from core.managers import get_gopro_manager
                gopro_manager = get_gopro_manager()
                if gopro_manager:
                    gopro_manager.on_gopro_status(msg)
            elif msg_type == 'gopro_result':
                from core.managers import get_gopro_manager
                gopro_manager = get_gopro_manager()
                if gopro_manager:
                    gopro_manager.on_gopro_result(msg)

    def _on_error(self, ws, error):
        """Handle WebSocket error - RUNS IN WEBSOCKET THREAD"""
        self._log("error", f"WebSocket error: {error}")

    def _on_open(self, ws):
        """Handle WebSocket open"""
        self.connected = True
        self._log("info", "WebSocket connection opened")
        
        # ✅ Re-register after reconnect
        if self.module_id:
            self._log("info", f"Re-registering as: {self.module_id}")
            
            # 1. Register
            app_port = self._get_config('APP_PORT', 8081)

            # Resolve absolute DB path from SQLAlchemy URI
            import os
            db_path = ''
            try:
                db_uri = self._get_config('SQLALCHEMY_DATABASE_URI', '')
                db_filename = db_uri.replace('sqlite:///', '').replace('sqlite://', '')
                if self.app:
                    db_path = os.path.join(self.app.instance_path, db_filename)
                else:
                    db_path = db_filename
            except Exception:
                pass
            
            self.send({
                'from': self.module_id,
                'to': 'hub',
                'type': 'register',
                'payload': {
                    'id': self.module_id,
                    'name': self.module_name or 'FUTSAL NALF',
                    'component_type': 'main_module',
                    'host': 'localhost',
                    'port': str(app_port),
                    'type': 'local',
                    'database_path': db_path
                }
            })
            
            # Wait a bit for registration
            time.sleep(0.5)
            
            # 2. Declare required plugins
            if self.required_plugins:
                self._log("info", f"Re-declaring {len(self.required_plugins)} required plugins")
                self.send({
                    'from': self.module_id,
                    'to': 'hub',
                    'type': 'declare_required_plugins',
                    'payload': {
                        'owner_id': self.module_id,
                        'plugins': self.required_plugins
                    }
                })
                
                time.sleep(0.5)
            
            # 3. Subscribe to classes
            if self.subscribe_classes:
                self._log("info", f"Re-subscribing to classes: {', '.join(self.subscribe_classes)}")
                self.send({
                    'from': self.module_id,
                    'to': 'hub',
                    'type': 'subscribe',
                    'payload': {
                        'class': self.subscribe_classes
                    }
                })

        # ✅ Fallback: jeśli po 10s dane nadal nie dotarły, wyślij ponowne żądanie
        self._ensure_plugins_ready(delay=10.0)

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        self.connected = False
        self._log("warning", f"WebSocket closed: {close_msg} (code: {close_status_code})")
        # ✅ Auto-reconnect wykryje disconnection i spróbuje ponownie

    def disconnect(self):
        """Disconnect from Hub"""
        self._log("info", "Disconnecting from Hub...")

        self._should_reconnect = False  # ✅ Wyłącz reconnect
        self.connected = False
        if self.ws:
            self.ws.close()

        self._log("info", "Disconnected from Hub")

    # =========================================================================
    # LATE-JOIN: reagowanie na pojawienie się pluginu w dowolnym momencie
    # =========================================================================

    def _on_plugin_connected(self, plugin_id: str):
        """
        Wywoływana gdy hub poinformuje nas, że plugin właśnie się połączył
        (niezależnie od tego czy stało się to przed czy po starcie main-module).
        """
        self._log("info", f"[late-join] Plugin connected: {plugin_id}")

        if plugin_id == 'obs-ws-plugin':
            self._request_obs_scene_map()

        if plugin_id.startswith('cam-head-'):
            from core.managers import get_servo_manager, get_gopro_manager
            servo_manager = get_servo_manager()
            if servo_manager:
                servo_manager.on_head_online(plugin_id)
            gopro_manager = get_gopro_manager()
            if gopro_manager:
                gopro_manager.on_head_online(plugin_id)

    def _request_obs_scene_map(self):
        """Prosi obs-ws-plugin o przesłanie aktualnej mapy scen."""
        self._log("info", "[late-join] Requesting OBS scene map from obs-ws-plugin")
        self.send({
            'from':    self.module_id or 'main-module',
            'to':      'obs-ws-plugin',
            'type':    'request_scene_map',
            'payload': {}
        })

    def _ensure_plugins_ready(self, delay: float = 10.0):
        """
        Fallback: po `delay` sekundach od rejestracji sprawdza, czy kluczowe
        dane zostały otrzymane. Jeśli nie — wysyła ponowne żądanie.
        Uruchamiany jako daemon thread po _on_open.
        """
        import threading, time

        def _check():
            time.sleep(delay)
            try:
                with self.app.app_context():
                    from core.managers import get_obs_ws_manager
                    obs = get_obs_ws_manager()
                    if not obs.get_scene_map():
                        self._log("warning",
                                  "[late-join] OBS scene map still empty after "
                                  f"{delay:.0f}s — re-requesting")
                        self._request_obs_scene_map()
            except Exception as e:
                self._log("error", f"[late-join] _ensure_plugins_ready failed: {e}")

        threading.Thread(target=_check, daemon=True).start()

    # def _handle_timer_updated(self, message):
    #     """Forward timer updates to TimerManager"""
    #     from core.managers import get_timer_manager
    #     timer_manager = get_timer_manager()
    #     if timer_manager:
    #         timer_manager.on_timer_updated(message.get('payload', {}))
    #
    # def _handle_timer_event(self, message):
    #     """Forward timer events to TimerManager"""
    #     from core.managers import get_timer_manager
    #     timer_manager = get_timer_manager()
    #     if timer_manager:
    #         timer_manager.on_timer_event(message.get('payload', {}))
    #
    # def _handle_timer_created(self, message):
    #     """Forward timer created to TimerManager"""
    #     from core.managers import get_timer_manager
    #     timer_manager = get_timer_manager()
    #     if timer_manager:
    #         # You can add on_timer_created method to TimerManager if needed
    #         payload = message.get('payload', {})
    #         self._log("info", f"Timer created: {payload.get('timer_id')}")

    # ========================================================================
    # HELPER METHODS - APP CONTEXT MANAGEMENT
    # ========================================================================

    def _with_app_context(self, func, *args, **kwargs):
        """Execute function within Flask app context"""
        if self.app:
            with self.app.app_context():
                return func(*args, **kwargs)
        else:
            return func(*args, **kwargs)

    def _log(self, level, message, exc_info=False):
        """Log message with or without app context"""
        if self.app:
            try:
                with self.app.app_context():
                    from flask import current_app
                    logger = current_app.logger

                    if level == 'debug':
                        logger.debug(message, exc_info=exc_info)
                    elif level == 'info':
                        logger.info(message, exc_info=exc_info)
                    elif level == 'warning':
                        logger.warning(message, exc_info=exc_info)
                    elif level == 'error':
                        logger.error(message, exc_info=exc_info)
            except:
                # Fallback to print if app context fails
                print(f"[{level.upper()}] {message}")
        else:
            # No app available, use print
            print(f"[{level.upper()}] {message}")

    def _get_config(self, key, default=None):
        """Get config value with or without app context"""
        if self.app:
            try:
                with self.app.app_context():
                    from flask import current_app
                    return current_app.config.get(key, default)
            except:
                return default
        return default