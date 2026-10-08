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
        self.gave_up = set()  # pluginy, którym HUB wyczerpał automatyczne próby restartu; do ich rejestracji
        self.unreachable = {}  # {plugin_id: polecenie, ktore nie dotarlo}; wpis znika po powrocie pluginu
        
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
                if plugins[plugin_id]['is_active']:
                    self.mark_reachable(plugin_id)

        for plugin_id, info in plugins_health.items():
            if plugin_id in plugins:
                plugins[plugin_id]['is_healthy'] = info.get('is_healthy', False)

        for plugin_id, entry in plugins.items():
            entry['unreachable'] = plugin_id in self.unreachable
            entry['gave_up'] = plugin_id in self.gave_up
        self._emit_to_ui('plugins_states', plugins)

    def mark_unreachable(self, plugin_id, command):
        """Plugin nie odebrał polecenia. Komunikat w panelu pojawia się raz na plugin (do jego powrotu)."""
        with self.lock:
            first = plugin_id not in self.unreachable
            self.unreachable[plugin_id] = command
        if first:
            self._emit_to_ui('plugin_unreachable', {'plugin_id': plugin_id, 'command': command})

    def mark_gave_up(self, plugin_id):
        """HUB poddał się z restartami pluginu. Trwały komunikat w panelu (raz), do rejestracji pluginu."""
        with self.lock:
            first = plugin_id not in self.gave_up
            self.gave_up.add(plugin_id)
        if first:
            current_app.logger.error(f"Plugin {plugin_id}: automatyczne próby restartu wyczerpane")
            self._emit_to_ui('plugin_gave_up', {'plugin_id': plugin_id})

    def mark_reachable(self, plugin_id):
        with self.lock:
            was = self.unreachable.pop(plugin_id, None) is not None
            was = (plugin_id in self.gave_up) or was
            self.gave_up.discard(plugin_id)
        if was:
            self._emit_to_ui('plugin_reachable', {'plugin_id': plugin_id})

    def _emit_to_ui(self, msg_type, data):
        """Emit event to UI clients via SocketIO"""
        try:
            from core.extensions import socketio
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f"Failed to emit to UI: {e}")