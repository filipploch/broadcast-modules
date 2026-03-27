import time
import threading
import importlib
import importlib.util


class SequenceManager:
    def __init__(self, hub_client, sequences_module_path: str):
        self.hub_client = hub_client
        self.sequences_module_path = sequences_module_path
        self.sequences = {}
        self.dynamic_sequences = {}
        self._running = {}
        self._lock = threading.Lock()
        self.load_sequences()

    def load_sequences(self):
        spec = importlib.util.spec_from_file_location("sequences", self.sequences_module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.sequences = module.SEQUENCES
        self.dynamic_sequences = getattr(module, 'DYNAMIC_SEQUENCES', {})

    def reload(self):
        """Przeładuj sekwencje bez restartu serwera"""
        self.load_sequences()

    def trigger(self, sequence_name: str, context: dict = None) -> str:
        steps = self.sequences.get(sequence_name)

        if steps is None:
            builder = self.dynamic_sequences.get(sequence_name)
            if builder:
                # steps = builder(**(context or {}))
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
        # Zarejestruj PRZED wykonaniem jakichkolwiek kroków
        with self._lock:
            self._running[sequence_id] = []

        by_delay = {}
        for step in steps:
            by_delay.setdefault(step.get("delay_ms", 0), []).append(step)

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

        with self._lock:
            if sequence_id in self._running:
                self._running[sequence_id] = timers

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

    def _execute_steps(self, steps: list, context: dict, sequence_id: str):
        with self._lock:
            if sequence_id not in self._running:
                return

        for step in steps:
            payload = {**step.get("payload", {})}
            if context:
                payload["_context"] = context
            self.hub_client.send({
                "from": "futsal-nalf",
                "to": step["target"],
                "type": step["action"],
                "payload": payload
            })