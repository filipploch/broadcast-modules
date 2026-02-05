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
        self.connected = False
        self.message_handlers = []
        self._lock = threading.Lock()

        # ✅ NEW: Subscribe classes support
        self.subscribe_classes = []

    def connect(self):
        """Connect to Hub"""
        self._log("info", f"Connecting to Hub: {self.hub_url}")

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
        """Run WebSocket connection"""
        while True:
            try:
                self.ws.run_forever()
            except Exception as e:
                self._log("error", f"WebSocket error: {e}")

            # Reconnect after delay
            if not self.connected:
                break

            self._log("info", "Reconnecting to Hub...")
            time.sleep(3)

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

        self._log("info", f"Registering as main module: {module_id}")

        # Get app_port from app config
        app_port = self._get_config('APP_PORT', 8081)

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
                'type': 'local'
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
            self._log("debug", f"Received: {msg_type} from {msg_from}")

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
                        print(f"Error in message handler: {e}")

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

        elif msg_type == 'plugin_online':
            plugin_id = payload.get('plugin_id')
            plugin_name = payload.get('plugin_name')
            self._log("info", f"Plugin online: {plugin_name} ({plugin_id})")

            # Update database
            # self._with_app_context(self._on_plugin_online, plugin_id, payload)

        elif msg_type == 'plugin_offline':
            plugin_id = payload.get('plugin_id')
            self._log("warning", f"Plugin offline: {plugin_id}")

            # Update database
            # self._with_app_context(self._on_plugin_offline, plugin_id)

        elif msg_type == 'health_status':
            print(f"health_status: {msg}")

        # elif msg_type == 'timer_updated':
        #     # Timer updates - forward to UI
        #     self._with_app_context(self._emit_to_ui, 'timer_updated', payload)

        # ✅ NEW: Handle timer limit reached
        # elif msg_type == 'timer_limit_reached':
        #     self._log("info", f"Timer limit reached: {payload.get('timer_id')}")
        #     self._with_app_context(self._emit_to_ui, 'timer_limit_reached', payload)

        # elif msg_type == 'recording_started':
        #     self._log("info", "Recording started")
        #     self._with_app_context(self._emit_to_ui, 'recording_status', {'recording': True})
        #
        # elif msg_type == 'recording_stopped':
        #     self._log("info", "Recording stopped")
        #     self._with_app_context(self._emit_to_ui, 'recording_status', {'recording': False})

        # Timer Plugin messages
        if msg_from == 'timer-plugin':
            from app.managers import get_timer_manager
            timer_manager = get_timer_manager()

            if msg_type == 'timer_updated':
                timer_manager.on_timer_updated(msg)
            elif msg_type == 'timer_event':
                timer_manager.on_timer_event(msg)
            elif msg_type == 'timer_created':
                timer_manager.on_timer_created(msg)
            elif msg_type == 'timer_started':
                timer_manager.on_timer_started(msg)
            elif msg_type == 'timer_paused':
                timer_manager.on_timer_paused(msg)
            elif msg_type == 'timer_reset':
                timer_manager.on_timer_reset(msg)
            elif msg_type == 'timer_adjusted':
                timer_manager.on_timer_adjusted(msg)
            elif msg_type == 'all_timers':
                timer_manager.on_all_timers(msg)
            elif msg_type == 'limit_reached':
                timer_manager.on_limit_reached(msg)

    # def _on_plugin_online(self, plugin_id, payload):
    #     """Handle plugin coming online"""
    #     # Update database
    #     from app.managers import get_plugin_manager
    #     plugin_manager = get_plugin_manager()
    #     if plugin_manager:
    #         plugin_manager.mark_plugin_online(plugin_id)

        # Emit to UI
        # self._emit_to_ui('plugin_status', {
        #     'plugin_id': plugin_id,
        #     'status': 'online'
        # })

        # Special handling for specific plugins
        # if plugin_id == 'recorder':
        #     from app.managers import get_recorder_manager
        #     recorder_manager = get_recorder_manager()
        #     if recorder_manager:
        #         recorder_manager.on_recorder_online()

    # def _on_plugin_offline(self, plugin_id):
    #     """Handle plugin going offline"""
    #     # Update database
    #     from app.managers import get_plugin_manager
    #     plugin_manager = get_plugin_manager()
    #     if plugin_manager:
    #         plugin_manager.mark_plugin_offline(plugin_id)

        # Emit to UI
        # self._emit_to_ui('plugin_status', {
        #     'plugin_id': plugin_id,
        #     'status': 'offline'
        # })

    # def _emit_to_ui(self, event, data):
    #     """Emit event to UI clients via SocketIO"""
    #     try:
    #         from app.extensions import socketio
    #         # socketio.emit(event, data, broadcast=True)
    #         socketio.emit(event, data)
    #     except Exception as e:
    #         self._log("error", f"Failed to emit to UI: {e}")

    def _on_error(self, ws, error):
        """Handle WebSocket error - RUNS IN WEBSOCKET THREAD"""
        self._log("error", f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close - RUNS IN WEBSOCKET THREAD"""
        self.connected = False
        self._log("warning", f"WebSocket closed: {close_msg} (code: {close_status_code})")

    def _on_open(self, ws):
        """Handle WebSocket open - RUNS IN WEBSOCKET THREAD"""
        self.connected = True
        self._log("info", "WebSocket connection opened")

    def disconnect(self):
        """Disconnect from Hub"""
        self._log("info", "Disconnecting from Hub...")

        self.connected = False
        if self.ws:
            self.ws.close()

        self._log("info", "Disconnected from Hub")

    # def _handle_timer_updated(self, message):
    #     """Forward timer updates to TimerManager"""
    #     from app.managers import get_timer_manager
    #     timer_manager = get_timer_manager()
    #     if timer_manager:
    #         timer_manager.on_timer_updated(message.get('payload', {}))
    #
    # def _handle_timer_event(self, message):
    #     """Forward timer events to TimerManager"""
    #     from app.managers import get_timer_manager
    #     timer_manager = get_timer_manager()
    #     if timer_manager:
    #         timer_manager.on_timer_event(message.get('payload', {}))
    #
    # def _handle_timer_created(self, message):
    #     """Forward timer created to TimerManager"""
    #     from app.managers import get_timer_manager
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