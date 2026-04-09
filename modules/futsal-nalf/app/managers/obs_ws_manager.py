"""OBS-Websocket Manager - Manages obs websocket plugin communication and state"""
from flask import current_app
from datetime import datetime
from app.models import Settings
from app.managers import GameEventManager
from app.managers import get_timer_manager
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
        if request_id is None:          # ← dodaj
            return  
        if request_id == 'get-websocket-connection':
            self._emit_to_ui('obs_status', 'connected')
        elif request_id.startswith('get-record-status-'):
                print(f'OBS_RESPONSE: {msg}')
                request_id = int(request_id.split('get-record-status-')[1])
                try:
                    from app.models.settings import Settings
                    settings = Settings.get_settings()
                    video_path = settings.get_obs_record_filepath()
                    # main_timer_id = settings.get_current_timers()['main']['timer_id']
                    # timer_manager = get_timer_manager()
                    # elapsed_time = timer_manager.get_timer_state(main_timer_id)['elapsed_time']
                    response_data = payload.get('responseData')
                    replay_end_time = response_data.get('outputDuration')
                    manager = GameEventManager()
                    manager.update_game_event(
                        game_event_id=request_id,
                        # game_time=int(elapsed_time/1000),
                        video_path=video_path,
                        replay_end_time=replay_end_time
                        )
                except Exception as e:
                    current_app.logger.error(f'❌ Failed to save game event: {e}')
                    self._emit_to_ui('error', {'message': str(e)})
                    return

    def on_obs_event(self, msg):
        payload = msg.get('payload')
        event_type = payload.get('eventType')
        event_data = payload.get('eventData')

        # Powiadom SequenceManager o każdym evencie OBS —
        # sekwencje z wait_for_obs_event czekają na konkretne typy eventów.
        try:
            from app.managers import get_sequence_manager
            seq_mgr = get_sequence_manager()
            if seq_mgr:
                seq_mgr.notify_obs_event(event_type, event_data)
        except Exception as e:
            current_app.logger.error(f"notify_obs_event failed: {e}")

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