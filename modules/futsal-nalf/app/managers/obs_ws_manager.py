"""OBS-Websocket Manager - Manages obs websocket plugin communication and state"""
from flask import current_app
from datetime import datetime
from app.models import Settings
# from app.managers import get_timer_manager
import threading


class ObsWsManager:
    """Manages communication with Timer Plugin and caches timer states"""
    
    def __init__(self, hub_client):
        """
        Initialize OBS-Websocket Manager
        
        Args:
            hub_client: HubClient instance for WebSocket communication
        """
        self.hub_client = hub_client
        # plugin_manager = get_timer_manager()
        self.obs_ws_plugin_id = 'obs-ws-plugin'
        self.lock = threading.Lock()
        
        current_app.logger.info("ObsWsManager initialized")

    def _emit_to_ui(self, msg_type, data):
        """Emit event to UI clients via SocketIO"""
        try:
            from app.extensions import socketio
            # socketio.emit(event, data, broadcast=True)
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f"Failed to emit to UI: {e}")

    def on_obs_status(self, msg):
        msg_type = msg.get('type')
        payload = msg.get('payload')
        status = payload.get('status')
        self._emit_to_ui(msg_type, status)

    def on_obs_response(self, msg):
        payload = msg.get('payload')
        request_id = payload.get('requestID')
        if request_id == 'get-websocket-connection':
            self._emit_to_ui('obs_status', 'connected')

    def on_obs_event(self, msg):
        payload = msg.get('payload')
        event_type = payload.get('eventType')
        event_data = payload.get('eventData')
        if event_type == 'RecordStateChanged':
            output_state = event_data.get('outputState')
            match output_state:
                case 'OBS_WEBSOCKET_OUTPUT_STARTING' | 'OBS_WEBSOCKET_OUTPUT_STOPPING':
                    self._emit_to_ui('obs_record_state', {'state': 'changing'})
                case 'OBS_WEBSOCKET_OUTPUT_STARTED':
                    obs_record_filepath = event_data.get('outputPath')
                    Settings.set_obs_record_filepath(obs_record_filepath)
                    self._emit_to_ui('obs_record_state', {'state': 'active'})
                case 'OBS_WEBSOCKET_OUTPUT_STOPPED':
                    obs_record_filepath = ''
                    Settings.set_obs_record_filepath(obs_record_filepath)
                    self._emit_to_ui('obs_record_state', {'state': 'disabled'})