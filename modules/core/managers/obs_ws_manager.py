"""OBS-Websocket Manager - Manages obs websocket plugin communication and state"""
from flask import current_app
from datetime import datetime
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

        # Pending synchronous requests: { request_id: threading.Event }
        # Odpowiedź trafia do _pending_responses: { request_id: dict }
        self._pending_requests:  dict = {}
        self._pending_responses: dict = {}
        self._pending_lock = threading.Lock()


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
            request_id = int(request_id.split('get-record-status-')[1])
            try:
                from core.models.base_settings import get_settings_model
                Settings = get_settings_model()
                settings       = Settings.get_settings()
                video_path     = settings.get_obs_record_filepath()
                response_data  = payload.get('responseData')
                replay_end_time = response_data.get('outputDuration')
                manager = GameEventManager()
                game_event = manager.update_game_event(
                    game_event_id=request_id,
                    video_path=video_path,
                    replay_end_time=replay_end_time
                )

                # Auto-trigger powtórki jeśli zdarzenie to bramka
                # W przyszłości: sprawdzaj pole Event.auto_replay zamiast nazwy
                _is_goal = False
                if game_event:
                    try:
                        from core.models.base_event import get_event_model
                        Event = get_event_model()
                        ev = Event.query.get(game_event.event_id)
                        _is_goal = ev is not None and ev.name.lower() == 'bramka'
                    except Exception:
                        pass
                if _is_goal:
                    from core.managers import get_hub_client
                    hub = get_hub_client()
                    if hub and game_event.video_path and game_event.replay_end_time:
                        hub.send({
                            'from':    current_app.config.get('MODULE_ID', 'main-module'),
                            'to':      'replay-plugin',
                            'type':    'replay_play',
                            'payload': {
                                'video_path':        game_event.video_path,
                                'replay_start_time': game_event.replay_start_time,
                                'replay_end_time':   game_event.replay_end_time,
                                'speed':             current_app.config.get('REPLAY_DEFAULT_SPEED', 0.9),
                            }
                        })
                        current_app.logger.info(
                            f'[replay] auto-trigger: game_event_id={game_event.id}'
                        )
            except Exception as e:
                current_app.logger.error(f'❌ Failed to save game event: {e}')
                self._emit_to_ui('error', {'message': str(e)})
                return
        elif request_id == 'ui-obs-stream-status':
            response_data = payload.get('responseData', {})
            output_active = response_data.get('outputActive', False)
            state = 'active' if output_active else 'disabled'
            self._emit_to_ui('obs_stream_state', {'state': state})
            if output_active:
                self._session_update('on_obs_stream_started')
        elif request_id == 'ui-obs-record-status':
            response_data = payload.get('responseData', {})
            output_active = response_data.get('outputActive', False)
            state = 'active' if output_active else 'disabled'
            self._emit_to_ui('obs_record_state', {'state': state})
            if output_active:
                self._session_update('on_obs_recording_started')
        elif request_id.startswith('sync-request-'):
            self._handle_sync_request(payload=payload)
        elif request_id.startswith('rec-status-'):
            # 'get_record_status' z panelu rozsyła wspólne 'recording_command', które odbiera też obs-ws-plugin i odpowiada
            # obs_response. Stan nagrywania kamer obsługuje recorder_manager (odpowiedź pluginu nagrywania); ta odpowiedź
            # OBS jest zbędna (stan OBS zgłasza osobne zapytanie 'ui-obs-record-status').
            current_app.logger.debug(f'Pomijam odpowiedź OBS na zapytanie o stan kamer: {request_id}')
        else:
            current_app.logger.warning(f"Unhandled OBS response requestID={request_id}: {msg}")

    def _handle_sync_request(self, payload):
        request_id    = payload.get('requestID')
        response_data = payload.get('responseData') or {}

        media_cursor = response_data.get('mediaCursor')
        if media_cursor:
            current_app.config['MEDIA_CURSOR'] = media_cursor

        with self._pending_lock:
            event = self._pending_requests.pop(request_id, None)
            if event:
                self._pending_responses[request_id] = response_data
                event.set()

    # =========================================================================
    # WIDOCZNOŚĆ ŹRÓDEŁ OBS
    # =========================================================================

    def get_scene_item_id(self, scene_name: str, source_name: str) -> int | None:
        with self.lock:
            item_id = self._scene_map.get(scene_name, {}).get(source_name)
        return item_id

    def get_scene_item_enabled(self, scene_name: str, scene_item_id: int) -> bool | None:
        result = self.send_obs_request_sync('GetSceneItemEnabled', {
            'sceneName':   scene_name,
            'sceneItemId': scene_item_id,
        })
        return result.get('sceneItemEnabled') if result else None

    def get_scene_item_list(self, scene_name:str, source_type: str | None = None) -> list[dict]:
        """
        Zwraca listę źródeł w scenie OBS.
        Każdy element listy to dict:
            {
                'sourceName': str,
                'sceneItemId': int,
                'sceneItemEnabled': bool,
            }
        """
        result = self.send_obs_request_sync('GetSceneItemList', {
            'sceneName': scene_name,
        })
        if not result:
            return []
        items = result.get('sceneItems', [])
        if source_type:
            items = [item for item in items if item.get('sourceType') == source_type]
        return items

    def set_scene_item_enabled(self, scene_name: str, scene_item_id: int, enabled: bool):
        self.send_obs_request_sync('SetSceneItemEnabled', {
            'sceneName':        scene_name,
            'sceneItemId':      scene_item_id,
            'sceneItemEnabled': enabled,
        })

    def set_input_settings(self, input_name: str, settings: dict, overlay: bool = True):
        self.send_obs_request_sync('SetInputSettings', {
            'inputName':     input_name,
            'inputSettings': settings,
            'overlay':       overlay,
        })

    # sCameraN -> port streamowany przez recorder-plugin (StreamManager),
    # przypisywane kolejno camera1..camera4 od stream_port (domyślnie 9000) —
    # patrz NewRecorderManager w recorder.go.
    CAMERA_STREAM_PORTS = {
        'sCamera1': 9000,
        'sCamera2': 9001,
        'sCamera3': 9002,
        'sCamera4': 9003,
    }

    # camera_id (recorder-plugin, np. z segment_rotated) -> nazwa źródła OBS.
    CAMERA_ID_TO_SOURCE = {
        'camera1': 'sCamera1',
        'camera2': 'sCamera2',
        'camera3': 'sCamera3',
        'camera4': 'sCamera4',
    }

    # Poprzedni pełny zestaw (-fflags nobuffer -flags low_delay
    # -analyzeduration 0 -probesize 32) zamroził obraz na jednej klatce —
    # niemal na pewno przez -probesize 32 (to 32 BAJTY, nie kilobajty —
    # drastycznie za mało, żeby libavformat stabilnie i w sposób CIĄGŁY
    # rozpoznawał strumień MPEG-TS) i/lub -analyzeduration 0. Teraz tylko
    # -fflags nobuffer — sama w sobie nie dotyka wykrywania/analizy
    # strumienia, tylko każe nie buforować już rozpoznanych pakietów, więc
    # nie powinna powtórzyć tego problemu. TESTUJ PRZYROSTOWO: jeśli to
    # przejdzie stabilnie (ciągły obraz, nie tylko "się pojawił"), można
    # ostrożnie spróbować dołożyć "-flags low_delay" osobno (bezpieczne przy
    # streamie bez B-klatek, którym tu jest), ale -probesize/-analyzeduration
    # zostaw w spokoju albo użyj wartości rzędu dziesiątek KB / setek ms, nie
    # zera.
    CAMERA_STREAM_FFMPEG_OPTIONS = '-fflags nobuffer'

    def sync_camera_stream_sources(self, host: str):
        """
        Ustawia URL SRT KAŻDEGO źródła Multimedia sCamera1..sCamera4 (scena
        CAMERAS) na dany host, niezależnie od tego czy dana kamera faktycznie
        teraz nagrywa. Używane tylko do ręcznego resynchronizowania
        (resync_camera_stream_sources) — w normalnym działaniu URL każdego
        źródła jest ustawiany/czyszczony per-kamera przez
        set_camera_stream_url, dopiero gdy ta konkretna kamera zaczyna/
        kończy nagrywać (patrz RecorderManager._set_camera_stream_active).
        """
        for source_name, port in self.CAMERA_STREAM_PORTS.items():
            url = f'srt://{host}:{port}?mode=caller'
            current_app.logger.info(f'🔄 {source_name} -> {url}')
            self.set_input_settings(source_name, {
                'input':          url,
                'is_local_file':  False,
                'ffmpeg_options': self.CAMERA_STREAM_FFMPEG_OPTIONS,
            })

    def set_camera_stream_url(self, camera_id: str, host: str | None):
        """
        Ustawia URL SRT źródła odpowiadającego camera_id na dany host, albo
        czyści go (pusty input) gdy host is None. Wywoływane przy
        recording_started/recording_stopped tej kamery — recorder-pluginu
        StreamManager nasłuchuje SRT tylko podczas nagrywania, więc czyszczenie
        po zatrzymaniu zapobiega ciągłym nieudanym próbom połączenia OBS co
        ok. 10s, dopóki kamera znowu nie zacznie nagrywać.
        """
        source_name = self.CAMERA_ID_TO_SOURCE.get(camera_id)
        if not source_name:
            return
        port = self.CAMERA_STREAM_PORTS.get(source_name)
        if not port:
            return
        if host:
            url = f'srt://{host}:{port}?mode=caller'
        else:
            url = ''
        current_app.logger.info(f'🔄 {source_name} -> {url or "(cleared)"}')
        self.set_input_settings(source_name, {
            'input':          url,
            'ffmpeg_options': self.CAMERA_STREAM_FFMPEG_OPTIONS if url else '',
            'is_local_file': False,
        })

    def refresh_browser_source(self, input_name: str):
        self.send_obs_request_sync('PressInputPropertiesButton', {
            'inputName':    input_name,
            'propertyName': 'refreshnocache',
        })

    def restart_camera_stream_source(self, camera_id: str):
        """
        Zmusza OBS do ponownego połączenia z SRT source'em odpowiadającym
        danej kamerze recorder-pluginu — potrzebne po każdej rotacji
        segmentu, bo restart procesu nagrywającego na Debianie zrywa na
        chwilę zapis do loopbacku, przez co proces streamujący dostaje nowy
        socket nasłuchujący, a OBS (restart_on_activate=false) sam się do
        niego nie podłączy. Patrz RecorderManager.on_segment_rotated.

        UWAGA: zakłada, że "restart" to poprawna nazwa przycisku we
        właściwościach źródła ffmpeg_source dla wejścia sieciowego (nie
        pliku lokalnego) — do zweryfikowania na żywym OBS, tak jak przy
        polu "input" w sync_camera_stream_sources.
        """
        source_name = self.CAMERA_ID_TO_SOURCE.get(camera_id)
        if not source_name:
            return
        current_app.logger.info(f'🔁 Restarting OBS source {source_name} (camera={camera_id})')
        self.send_obs_request_sync('PressInputPropertiesButton', {
            'inputName':    source_name,
            'propertyName': 'restart',
        })

    def set_current_program_scene(self, scene_name: str):
        self.send_obs_request_sync('SetCurrentProgramScene', {
            'sceneName': scene_name,
        })

    def _session_update(self, action, **kwargs):
        """Zdarzenia OBS → stan sesji transmisji (start streamu/nagrywania ustawia 'na antenie'; zatrzymanie NIE zamyka sesji).

        Błąd w sesji nie może przerwać obsługi zdarzenia OBS. Po zmianie UI dostaje 'session_state'.
        """
        try:
            from core.managers import session_manager
            before = session_manager.get_open_session()
            before_status = before.status if before else None
            getattr(session_manager, action)(**kwargs)
            after = session_manager.get_open_session()
            if after is not None:
                self._emit_to_ui('session_state', session_manager.describe())
                if before_status != after.status:
                    current_app.logger.info(f'📡 Sesja transmisji: {before_status} → {after.status} ({action})')
        except Exception as e:
            current_app.logger.error(f'session {action} failed: {e}')

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

        if event_type == 'StreamStateChanged':
            output_state = event_data.get('outputState')
            match output_state:
                case 'OBS_WEBSOCKET_OUTPUT_STARTING' | 'OBS_WEBSOCKET_OUTPUT_STOPPING':
                    self._emit_to_ui('obs_stream_state', {'state': 'changing'})
                case 'OBS_WEBSOCKET_OUTPUT_STARTED':
                    self._emit_to_ui('obs_stream_state', {'state': 'active'})
                    self._session_update('on_obs_stream_started')
                case 'OBS_WEBSOCKET_OUTPUT_STOPPED':
                    self._emit_to_ui('obs_stream_state', {'state': 'disabled'})
                    current_app.logger.warning('⚠️  OBS stream stopped unexpectedly')
                    self._session_update('update_obs_state', streaming=False)   # sesji nie zamykamy

        if event_type == 'RecordStateChanged':
            from core.models.base_settings import get_settings_model
            Settings = get_settings_model()
            output_state = event_data.get('outputState')
            match output_state:
                case 'OBS_WEBSOCKET_OUTPUT_STARTING' | 'OBS_WEBSOCKET_OUTPUT_STOPPING':
                    self._emit_to_ui('obs_record_state', {'state': 'changing'})
                case 'OBS_WEBSOCKET_OUTPUT_STARTED':
                    obs_record_filepath = event_data.get('outputPath', '')
                    if obs_record_filepath:
                        Settings.set_obs_record_filepath(obs_record_filepath)
                        current_app.logger.info(f'📹 OBS recording started: {obs_record_filepath}')
                    else:
                        # OBS WebSocket < 5.5.4 sends empty outputPath on STARTED.
                        # The actual path arrives only in the STOPPED event.
                        current_app.logger.warning(
                            '⚠️  OBS RecordStateChanged(STARTED): outputPath is empty '
                            '(upgrade OBS WebSocket to ≥5.5.4 to fix this)'
                        )
                    self._emit_to_ui('obs_record_state', {'state': 'active'})
                    self._session_update('on_obs_recording_started')
                case 'OBS_WEBSOCKET_OUTPUT_STOPPED':
                    obs_record_filepath = event_data.get('outputPath', '')
                    if obs_record_filepath:
                        # STOPPED always carries the final file path — save it so
                        # any game event that was recorded without a path can be
                        # identified retrospectively.
                        Settings.set_obs_record_filepath(obs_record_filepath)
                        current_app.logger.info(f'📹 OBS recording saved: {obs_record_filepath}')
                    else:
                        Settings.set_obs_record_filepath('')
                    self._emit_to_ui('obs_record_state', {'state': 'disabled'})
                    self._session_update('update_obs_state', recording=False)   # sesji nie zamykamy

        if event_type == 'CurrentProgramSceneChanged':
            scene = (event_data or {}).get('sceneName')
            if scene:
                self._session_update('update_obs_state', scene=scene)

        if event_type == 'SceneItemEnableStateChanged':
            scene_name    = event_data.get('sceneName')
            scene_item_id = event_data.get('sceneItemId')
            enabled       = event_data.get('sceneItemEnabled')
            with self.lock:
                source_name = next(
                    (k for k, v in self._scene_map.get(scene_name, {}).items() if v == scene_item_id),
                    None
                )
            if source_name:
                self._emit_to_ui('source_visibility_changed', {
                    'scene_name':  scene_name,
                    'source_name': source_name,
                    'enabled':     enabled,
                })

    def send_obs_request_sync(self, request_type: str, request_data: dict,
                              timeout: float = 2.0) -> dict | None:
        """
        Wysyła komendę OBS i synchronicznie czeka na odpowiedź.
        Zwraca payload odpowiedzi lub None przy timeout.
        """
        import datetime
        request_id = f'sync-request-{str(datetime.datetime.now()).replace(' ', '_')}'
        event = threading.Event()

        with self._pending_lock:
            self._pending_requests[request_id] = event

        self.hub_client.send({
            'from':    'main-module',
            'to':      'obs-ws-plugin',
            'type':    'obs_command',
            'payload': {
                'requestType': request_type,
                'requestData': request_data,
                'request_id':   request_id,
            }
        })

        if not event.wait(timeout=timeout):
            with self._pending_lock:
                self._pending_requests.pop(request_id, None)
            return None

        with self._pending_lock:
            return self._pending_responses.pop(request_id, None)

    def enable_source_filter(self, source_name, filter_name, filter_state=True):
        _request_type = 'SetSourceFilterEnabled'
        _request_data = {
            'sourceName': source_name,
            'filterName': filter_name,
            'filterEnabled': filter_state,
            }
        self.send_obs_request_sync(_request_type, _request_data)