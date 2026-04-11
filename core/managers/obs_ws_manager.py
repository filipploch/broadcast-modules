"""OBS-Websocket Manager - Manages obs websocket plugin communication and state"""
from flask import current_app
from datetime import datetime
from core.models import Settings
from core.managers.game_event_manager import GameEventManager
from core.managers import get_timer_manager
import threading


class ObsWsManager:
    """Manages communication with OBS WebSocket plugin"""

    def __init__(self, hub_client):
        self.hub_client = hub_client
        self.obs_ws_plugin_id = 'obs-ws-plugin'
        self.lock = threading.Lock()

        # Mapa scen OBS: { sceneName: { sourceName: sceneItemId } }
        # Wypełniana przez on_obs_scene_map() po każdym połączeniu pluginu z OBS.
        self._scene_map: dict = {}

        current_app.logger.info("ObsWsManager initialized")

    # =========================================================================
    # MAPA SCEN — wypełniana przez plugin przy każdym połączeniu z OBS
    # =========================================================================

    def on_obs_scene_map(self, msg):
        """
        Odbiera mapę scen z obs-ws-plugin i przechowuje ją lokalnie.
        Wywoływana przez hub_client gdy nadejdzie wiadomość obs_scene_map.

        Struktura msg.payload.scene_map:
            {
              "OUTPUT": { "Replay": 6, "Camera1": 3, ... },
              "AUDIO_SOURCES": { "Mic1": 2, "Mic2": 3 },
              ...
            }
        """
        payload   = msg.get('payload', {})
        scene_map = payload.get('scene_map', {})

        with self.lock:
            self._scene_map = scene_map

        scene_count  = len(scene_map)
        source_count = sum(len(v) for v in scene_map.values())
        current_app.logger.info(
            f"🗺️  OBS scene map updated: {scene_count} scene(s), "
            f"{source_count} source(s) total"
        )
        self._emit_to_ui('obs_scene_map', scene_map)

    def get_scene_map(self) -> dict:
        """Zwraca kopię aktualnej mapy scen (do debugowania/UI)."""
        with self.lock:
            return dict(self._scene_map)

    # =========================================================================
    # HANDLERY WIADOMOŚCI OBS
    # =========================================================================

    def _emit_to_ui(self, msg_type, data):
        """Emit event to UI clients via SocketIO"""
        try:
            from core.extensions import socketio
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f"Failed to emit to UI: {e}")

    def on_obs_status(self, msg):
        msg_type = msg.get('type')
        payload  = msg.get('payload')
        status   = payload.get('status')
        self._emit_to_ui(msg_type, status)

    def on_obs_response(self, msg):
        payload    = msg.get('payload')
        request_id = payload.get('requestID')
        if request_id is None:
            return
        if request_id == 'get-websocket-connection':
            self._emit_to_ui('obs_status', 'connected')
        elif request_id.startswith('get-record-status-'):
            print(f'OBS_RESPONSE: {msg}')
            request_id = int(request_id.split('get-record-status-')[1])
            try:
                from core.models.settings import Settings
                settings       = Settings.get_settings()
                video_path     = settings.get_obs_record_filepath()
                response_data  = payload.get('responseData')
                replay_end_time = response_data.get('outputDuration')
                manager = GameEventManager()
                manager.update_game_event(
                    game_event_id=request_id,
                    video_path=video_path,
                    replay_end_time=replay_end_time
                )
            except Exception as e:
                current_app.logger.error(f'❌ Failed to save game event: {e}')
                self._emit_to_ui('error', {'message': str(e)})
                return

    def on_obs_event(self, msg):
        payload    = msg.get('payload')
        event_type = payload.get('eventType')
        event_data = payload.get('eventData')

        # Powiadom SequenceManager o każdym evencie OBS
        try:
            from core.managers import get_sequence_manager
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
