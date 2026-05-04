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
            # 'obs-ws-plugin': {},
            'recorder-plugin': {},
            'timer-plugin': {}
        }

        for _plugin in connected_plugins:
            if connected_plugins[_plugin]['plugin_id'] in plugins:
                plugins[_plugin].update({'is_active': connected_plugins[_plugin]['is_active']})

        for _plugin in plugins_health:
            if plugins_health[_plugin]['plugin_id'] in plugins:
                plugins[_plugin].update({'is_healthy': plugins_health[_plugin]['is_healthy']})

        self._emit_to_ui('plugins_states', plugins)

    def _emit_to_ui(self, msg_type, data):
        """Emit event to UI clients via SocketIO"""
        try:
            from core.extensions import socketio
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f"Failed to emit to UI: {e}")