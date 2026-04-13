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

       Listener jest rejestrowany natychmiast przy starcie sekwencji,
       ale zapamiętuje swój czas rejestracji (registered_at). Eventy
       które nadeszły PRZED tym czasem są odrzucane — rozwiązuje to
       problem fałszywych eventów emitowanych przez OBS przy ładowaniu
       pliku (np. MediaInputPlaybackStarted przy SetInputSettings),
       które mogą przyjść zanim właściwy PLAY zostanie wysłany.

       Opcjonalne timeout_ms — jeśli event nie nadejdzie w zadanym czasie
       od rejestracji listenera, krok jest pomijany z ostrzeżeniem.

    Przykład:
        start_replay(delay_ms=800),
        set_replay_start_time(t,
            wait_for_obs_event='MediaInputPlaybackStarted',
            timeout_ms=5000)

    Notyfikowanie o eventach OBS
    ----------------------------
    ObsWsManager.on_obs_event() powinien wołać:
        sequence_manager.notify_obs_event(event_type, event_data)
    """

    def __init__(self, hub_client, sequences_module_path: str):
        self.hub_client = hub_client
        self.sequences_module_path = sequences_module_path
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

        timer_steps = []
        event_steps = []

        for step in steps:
            if step.get('wait_for_obs_event'):
                event_steps.append(step)
            else:
                timer_steps.append(step)

        # Listenery eventowe rejestrujemy NA POCZĄTKU sekwencji —
        # zapamiętują swój registered_at i odrzucają starsze eventy.
        # Muszą być gotowe zanim jakikolwiek krok czasowy zostanie wysłany.
        listeners = []
        for step in event_steps:
            listener = _EventListener(
                event_type=step['wait_for_obs_event'],
                timeout_ms=step.get('timeout_ms', 5000),
            )
            with self._obs_lock:
                if listener.event_type not in self._obs_event_listeners:
                    self._obs_event_listeners[listener.event_type] = []
                self._obs_event_listeners[listener.event_type].append(listener)
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

        # --- Kroki eventowe: każdy czeka na swój listener ---
        for step, listener in listeners:
            t = threading.Thread(
                target=self._run_event_step,
                args=[step, listener, context, sequence_id],
                daemon=True
            )
            timers.append(t)
            t.start()

        with self._lock:
            if sequence_id in self._running:
                self._running[sequence_id] = timers

    def _run_event_step(self, step: dict, listener: '_EventListener',
                        context: dict, sequence_id: str):
        """
        Czeka aż listener otrzyma event OBS (nowszy niż czas rejestracji listenera).
        """
        triggered = listener.wait()

        # Usuń listener niezależnie od wyniku
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
    # NOTYFIKACJE O EVENTACH OBS
    # =========================================================================

    def notify_obs_event(self, event_type: str, event_data: dict = None):
        """
        Wywoływane przez ObsWsManager gdy nadejdzie obs_event z pluginu.
        Przekazuje event do listenerów — każdy samodzielnie decyduje czy
        event jest wystarczająco nowy (arrived_at > registered_at).
        """
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

            # obs_command_by_name: plugin Go rozwiązuje sourceName → sceneItemId
            # Wysyłamy payload z sceneName + sourceName bez zmian —
            # resolucja odbywa się w obs-ws-plugin, nie tutaj.
            self.hub_client.send({
                'from': 'main-module',
                'to': step['target'],
                'type': step['action'],
                'payload': payload
            })


class _EventListener:
    """
    Listener czekający na jeden konkretny event OBS.

    registered_at (time.monotonic()) jest zapamiętywany w momencie
    tworzenia obiektu. notify() akceptuje event tylko jeśli arrived_at
    jest późniejszy niż registered_at — odrzuca eventy "sprzed rejestracji"
    które OBS emituje przy ładowaniu pliku lub resecie źródła.
    """

    def __init__(self, event_type: str, timeout_ms: int = 5000):
        self.event_type   = event_type
        self.timeout_ms   = timeout_ms
        self.registered_at = time.monotonic()
        self._event       = threading.Event()

    def notify(self, arrived_at: float) -> bool:
        """
        Przyjmuje event jeśli arrived_at > registered_at.
        Zwraca True jeśli event został zaakceptowany, False jeśli odrzucony.
        """
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
        """Czeka na event. Zwraca True jeśli nadszedł, False jeśli timeout."""
        return self._event.wait(timeout=self.timeout_ms / 1000)
