import time
import threading
import importlib
import importlib.util
import logging

logger = logging.getLogger(__name__)


class SequenceManager:
    """
    Wykonuje sekwencje kroków kierowanych do pluginów przez hub.

    Typy kroków
    -----------

    1. delay_ms  — krok wykonywany po upływie czasu od startu sekwencji.

    2. wait_for_obs_event  — krok wykonywany po nadejściu eventu OBS.

    3. action == 'watch_media_cursor'  — krok złożony wykonywany w osobnym wątku:
         a) co poll_interval_ms pyta OBS o GetMediaInputStatus
         b) gdy mediaCursor >= min_cursor_ms — pokazuje źródło
         c) po visible_duration_ms ukrywa źródło
         d) jeśli timeout_ms minie bez sukcesu — przerywa cicho

    Notyfikowanie o eventach OBS
    ----------------------------
    ObsWsManager.on_obs_event() powinien wołać:
        sequence_manager.notify_obs_event(event_type, event_data)
    """

    def __init__(self, hub_client, sequences_module_path: str, app=None):
        self.hub_client = hub_client
        self.sequences_module_path = sequences_module_path
        self.app = app
        self.sequences = {}
        self.dynamic_sequences = {}

        self._running = {}
        self._lock = threading.Lock()

        # { event_type: [ _EventListener, ... ] }
        self._obs_event_listeners: dict = {}
        self._obs_lock = threading.Lock()

        self.load_sequences()

    # =========================================================================
    # ŁADOWANIE SEKWENCJI
    # =========================================================================

    def load_sequences(self):
        spec = importlib.util.spec_from_file_location("sequences", self.sequences_module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.sequences = module.SEQUENCES
        self.dynamic_sequences = getattr(module, 'DYNAMIC_SEQUENCES', {})

    def reload(self):
        self.load_sequences()

    # =========================================================================
    # URUCHAMIANIE SEKWENCJI
    # =========================================================================

    def trigger(self, sequence_name: str, context: dict = None) -> str:
        steps = self.sequences.get(sequence_name)

        if steps is None:
            builder = self.dynamic_sequences.get(sequence_name)
            if builder:
                steps = builder(context or {})

        if steps is None:
            raise ValueError(f"Unknown sequence: {sequence_name}")

        sequence_id = f"{sequence_name}_{time.time_ns()}"

        t = threading.Thread(
            target=self._run_sequence,
            args=[steps, context, sequence_id],
            daemon=True
        )
        t.start()

        return sequence_id

    def _run_sequence(self, steps: list, context: dict, sequence_id: str):
        with self._lock:
            self._running[sequence_id] = []

        timer_steps   = []
        event_steps   = []
        special_steps = []

        for step in steps:
            if step.get('action') == 'watch_media_cursor':
                special_steps.append(step)
            elif step.get('wait_for_obs_event'):
                event_steps.append(step)
            else:
                timer_steps.append(step)

        # Listenery eventowe rejestrujemy NA POCZĄTKU sekwencji
        listeners = []
        for step in event_steps:
            listener = _EventListener(
                event_type=step['wait_for_obs_event'],
                timeout_ms=step.get('timeout_ms', 5000),
            )
            with self._obs_lock:
                self._obs_event_listeners.setdefault(listener.event_type, []).append(listener)
            listeners.append((step, listener))
            logger.debug(
                f"[SequenceManager] Listener '{listener.event_type}' zarejestrowany "
                f"na starcie sekwencji (registered_at={listener.registered_at:.4f})"
            )

        # --- Kroki czasowe (delay_ms) ---
        by_delay = {}
        for step in timer_steps:
            by_delay.setdefault(step.get('delay_ms', 0), []).append(step)

        timers = []
        for delay_ms, delay_steps in sorted(by_delay.items()):
            if delay_ms == 0:
                self._execute_steps(delay_steps, context, sequence_id)
            else:
                t = threading.Timer(
                    delay_ms / 1000,
                    self._execute_steps,
                    args=[delay_steps, context, sequence_id]
                )
                timers.append(t)
                t.start()

        # --- Kroki eventowe ---
        for step, listener in listeners:
            t = threading.Thread(
                target=self._run_event_step,
                args=[step, listener, context, sequence_id],
                daemon=True
            )
            timers.append(t)
            t.start()

        # --- Kroki specjalne: watch_media_cursor ---
        for step in special_steps:
            t = threading.Thread(
                target=self._watch_media_cursor,
                args=[step['payload'], sequence_id],
                daemon=True
            )
            timers.append(t)
            t.start()

        with self._lock:
            if sequence_id in self._running:
                self._running[sequence_id] = timers

    def _run_event_step(self, step: dict, listener: '_EventListener',
                        context: dict, sequence_id: str):
        triggered = listener.wait()

        with self._obs_lock:
            bucket = self._obs_event_listeners.get(listener.event_type, [])
            if listener in bucket:
                bucket.remove(listener)

        if not triggered:
            logger.warning(
                f"[SequenceManager] Krok '{step.get('action')}' pominięty — "
                f"event '{listener.event_type}' nie nadszedł w ciągu "
                f"{listener.timeout_ms}ms od rejestracji"
            )
            return

        self._execute_steps([step], context, sequence_id)

    # =========================================================================
    # WATCH MEDIA CURSOR
    # =========================================================================

    def _watch_media_cursor(self, payload: dict, sequence_id: str):
        """
        Polluje GetMediaInputStatus co poll_interval_ms.
        Gdy mediaCursor >= min_cursor_ms — pokazuje źródło source_name w scenie scene_name,
        a po visible_duration_ms ukrywa je.
        Jeśli timeout_ms minie — przerywa cicho.
        """
        scene_name          = payload.get('scene_name',          'OUTPUT')
        source_name         = payload.get('source_name',         'Replay')
        poll_interval_ms    = payload.get('poll_interval_ms',    250)
        min_cursor_ms       = payload.get('min_cursor_ms',       2000)
        visible_duration_ms = payload.get('visible_duration_ms', 10000)
        timeout_ms          = payload.get('timeout_ms',          30000)

        deadline = time.monotonic() + timeout_ms / 1000
        logger.debug(
            f"[watch_media_cursor] Start — czekam aż cursor >= {min_cursor_ms}ms "
            f"(timeout={timeout_ms}ms, poll={poll_interval_ms}ms)"
        )

        while time.monotonic() < deadline:
            cursor = self._get_media_cursor(source_name)
            logger.debug(f"[watch_media_cursor] cursor={cursor}")

            if cursor is not None and cursor >= min_cursor_ms:
                logger.debug(
                    f"[watch_media_cursor] cursor={cursor}ms >= {min_cursor_ms}ms "
                    f"— pokazuję {source_name}"
                )
                self._send_show_source(scene_name, source_name, visible=True)

                # Ukryj po visible_duration_ms
                t = threading.Timer(
                    visible_duration_ms / 1000,
                    self._send_show_source,
                    args=[scene_name, source_name, False]
                )
                t.start()
                return

            time.sleep(poll_interval_ms / 1000)

        logger.warning(
            f"[watch_media_cursor] Timeout {timeout_ms}ms — "
            f"cursor nigdy nie osiągnął {min_cursor_ms}ms"
        )

    def _get_media_cursor(self, input_name: str):
        """
        Pyta OBS o aktualną pozycję kursora źródła media.
        Używa send_obs_request_sync z ObsWsManager.
        Zwraca int (ms) lub None.
        """
        with self.app.app_context():
            try:
                from core.managers import get_obs_ws_manager
                
                obs_mgr  = get_obs_ws_manager()
                obs_mgr.send_obs_request_sync(
                    'GetMediaInputStatus',
                    {'inputName': input_name},
                    timeout=2.0
                )
                cursor = self.app.config['MEDIA_CURSOR']
                return int(cursor) if cursor is not None else None
            except Exception as e:
                logger.warning(f"[watch_media_cursor] Błąd GetMediaInputStatus: {e}")
                return None

    def _send_show_source(self, scene_name: str, source_name: str, visible: bool):
        self.hub_client.send({
            'from':    'main-module',
            'to':      'obs-ws-plugin',
            'type':    'obs_command_by_name',
            'payload': {
                'requestType': 'SetSceneItemEnabled',
                'sceneName':   scene_name,
                'sourceName':  source_name,
                'requestData': {
                    'sceneName':        scene_name,
                    'sceneItemEnabled': visible,
                }
            }
        })
        logger.debug(
            f"[watch_media_cursor] show_source({source_name}, visible={visible})"
        )

    # =========================================================================
    # NOTYFIKACJE O EVENTACH OBS
    # =========================================================================

    def notify_obs_event(self, event_type: str, event_data: dict = None):
        arrived_at = time.monotonic()

        with self._obs_lock:
            listeners = list(self._obs_event_listeners.get(event_type, []))

        notified = 0
        for listener in listeners:
            if listener.notify(arrived_at):
                notified += 1

        logger.debug(
            f"[SequenceManager] notify_obs_event '{event_type}' arrived_at={arrived_at:.4f} "
            f"→ zaakceptowano przez {notified}/{len(listeners)} listener(ów)"
        )

    # =========================================================================
    # ZATRZYMYWANIE SEKWENCJI
    # =========================================================================

    def stop(self, sequence_id: str):
        with self._lock:
            timers = self._running.pop(sequence_id, [])
        for t in timers:
            t.cancel()

    def stop_all(self, sequence_name: str = None):
        with self._lock:
            if sequence_name:
                to_stop = {k: v for k, v in self._running.items()
                           if k.startswith(sequence_name)}
            else:
                to_stop = dict(self._running)
            for key in to_stop:
                del self._running[key]

        for timers in to_stop.values():
            for t in timers:
                t.cancel()

    # =========================================================================
    # WYKONYWANIE KROKÓW
    # =========================================================================

    def _execute_steps(self, steps: list, context: dict, sequence_id: str):
        with self._lock:
            if sequence_id not in self._running:
                return

        for step in steps:
            payload = {**step.get('payload', {})}
            if context:
                payload['_context'] = context

            self.hub_client.send({
                'from':    'main-module',
                'to':      step['target'],
                'type':    step['action'],
                'payload': payload
            })


class _EventListener:
    """
    Listener czekający na jeden konkretny event OBS.
    registered_at odrzuca eventy sprzed rejestracji.
    """

    def __init__(self, event_type: str, timeout_ms: int = 5000):
        self.event_type    = event_type
        self.timeout_ms    = timeout_ms
        self.registered_at = time.monotonic()
        self._event        = threading.Event()

    def notify(self, arrived_at: float) -> bool:
        if arrived_at <= self.registered_at:
            logger.debug(
                f"[_EventListener] '{self.event_type}' odrzucony — "
                f"arrived_at={arrived_at:.4f} <= registered_at={self.registered_at:.4f} "
                f"(różnica: {(arrived_at - self.registered_at)*1000:.1f}ms)"
            )
            return False
        self._event.set()
        return True

    def wait(self) -> bool:
        return self._event.wait(timeout=self.timeout_ms / 1000)
