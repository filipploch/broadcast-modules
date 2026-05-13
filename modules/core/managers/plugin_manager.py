"""Plugin Manager - Manages timer plugin communication and state"""
from flask import current_app
from datetime import datetime
# from core.managers import get_timer_manager
import threading


class PluginManager:
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
        
        current_app.logger.info("PluginManager initialized")

    def on_plugins_state_received(self, msg):
        msg_type = msg.get('type')
        payload = msg.get('payload')
        connected_plugins = payload.get('connected_plugins')
        plugins_health = payload.get('plugin_health')

        plugins = {
            'timer-plugin':      {'is_active': False, 'is_healthy': False},
            'recorder-plugin':   {'is_active': False, 'is_healthy': False},
            'obs-ws-plugin':     {'is_active': False, 'is_healthy': False},
            'replay-plugin':     {'is_active': False, 'is_healthy': False},
            'controller-plugin': {'is_active': False, 'is_healthy': False},
            'stream-overlay':    {'is_active': False, 'is_healthy': False},
        }

        for plugin_id, info in connected_plugins.items():
            if plugin_id in plugins:
                plugins[plugin_id]['is_active'] = info.get('is_active', False)

        for plugin_id, info in plugins_health.items():
            if plugin_id in plugins:
                plugins[plugin_id]['is_healthy'] = info.get('is_healthy', False)

        self._emit_to_ui('plugins_states', plugins)

    def _emit_to_ui(self, msg_type, data):
        """Emit event to UI clients via SocketIO"""
        try:
            from core.extensions import socketio
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f"Failed to emit to UI: {e}")