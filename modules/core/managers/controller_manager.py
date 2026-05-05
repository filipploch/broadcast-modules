"""
core.managers.controller_manager — łącznik między controller-plugin
a replay-plugin.

Trzyma jedyne źródło prawdy o stanie powtórki (idle/playing/paused) i bieżącej
prędkości. Stan aktualizowany jest na podstawie sygnałów z replay-plugin
(replay_started, replay_paused, replay_resumed, replay_done).

Dla każdego zdarzenia z controller-plugin (controller_button / controller_wheel)
dobiera odpowiedni sygnał replay_* na podstawie stanu i wysyła go do hub'a.

Po każdej zmianie stanu emituje socketio event 'replay_state_changed' do UI,
żeby przyciski pause/resume i ewentualne wskaźniki prędkości pozostały
zsynchronizowane gdy operator używa kontrolera (a nie kliknie w UI).
"""

import threading


class ControllerManager:
    SPEED_MIN = 0.3
    SPEED_MAX = 0.9
    SPEED_STEP = 0.05
    # Limit liczby krok-klatek wysyłanych z jednego eventu rolki.
    # Zapobiega zalewaniu workerа replay-plugin gdy ktoś zakręci rolką
    # bardzo szybko (controller-plugin zsumuje tiki, ale my i tak chcemy
    # cap żeby nie wysyłać 50 frame_forward jednym strzałem).
    FRAME_STEP_MAX_PER_EVENT = 10

    def __init__(self, hub_client, default_speed=0.9):
        self.hub_client = hub_client
        self._lock = threading.Lock()
        self.status = 'idle'                    # 'idle' | 'playing' | 'paused'
        self.current_speed = float(default_speed)
        self.default_speed = float(default_speed)
        self._app = None

    def attach_app(self, app):
        """Ustawia referencję do Flask app — niezbędne dla socketio.emit
        wywoływanego z wątku websocket'a."""
        self._app = app

    # ── Aktualizacja stanu z sygnałów replay-plugin ──────────────────────────

    def on_replay_started(self, payload):
        with self._lock:
            self.status = 'playing'
            speed = payload.get('speed') if payload else None
            if speed is not None:
                try:
                    self.current_speed = float(speed)
                except (TypeError, ValueError):
                    pass
        self._emit_state()

    def on_replay_paused(self, payload):
        with self._lock:
            self.status = 'paused'
        self._emit_state()

    def on_replay_resumed(self, payload):
        with self._lock:
            self.status = 'playing'
        self._emit_state()

    def on_replay_done(self, payload):
        with self._lock:
            self.status = 'idle'
            self.current_speed = self.default_speed
        self._emit_state()

    # ── Obsługa zdarzeń controller-plugin ────────────────────────────────────

    def on_controller_button(self, payload):
        """payload = { button: 'wheel_btn'|'btn1'|'btn2'|'btn3', action: 'press'|'release' }"""
        if not payload:
            return
        button = payload.get('button')
        action = payload.get('action', 'press')
        if action != 'press':
            return  # reagujemy wyłącznie na press

        with self._lock:
            status = self.status

        self._log(f"button={button} (status={status})")

        if status == 'idle':
            return  # poza powtórką wszystkie przyciski no-op

        if button == 'wheel_btn':
            # Toggle pauza/wznów na podstawie aktualnego stanu
            if status == 'playing':
                self._send_replay('replay_pause', {})
            elif status == 'paused':
                self._send_replay('replay_resume', {})
        elif button == 'btn3':
            # Manualne zakończenie powtórki
            self._send_replay('end_replay', {})
        # btn1 / btn2 — niezaalokowane

    def on_controller_wheel(self, payload):
        """payload = { delta: int }   (+ = clockwise, - = counter-clockwise)"""
        if not payload:
            return
        try:
            delta = int(payload.get('delta', 0))
        except (TypeError, ValueError):
            return
        if delta == 0:
            return

        with self._lock:
            status = self.status
            current_speed = self.current_speed

        self._log(f"wheel delta={delta:+d} (status={status})")

        if status == 'playing':
            # Zmiana tempa
            new_speed = current_speed + delta * self.SPEED_STEP
            new_speed = max(self.SPEED_MIN, min(self.SPEED_MAX, new_speed))
            new_speed = round(new_speed, 3)
            if abs(new_speed - current_speed) < 1e-6:
                return  # już na granicy zakresu — nic nie zmieniamy
            with self._lock:
                self.current_speed = new_speed
            self._send_replay('replay_speed', {'speed': new_speed})
            self._emit_state()

        elif status == 'paused':
            # Frame-step: jeden replay_frame_* per tick (z capem)
            sig = 'replay_frame_forward' if delta > 0 else 'replay_frame_back'
            steps = min(abs(delta), self.FRAME_STEP_MAX_PER_EVENT)
            for _ in range(steps):
                self._send_replay(sig, {})

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _send_replay(self, signal, payload):
        if not self.hub_client:
            return
        try:
            self.hub_client.send({
                'from':    'main-module',
                'to':      'replay-plugin',
                'type':    signal,
                'payload': payload,
            })
        except Exception as e:
            self._log(f"send {signal} failed: {e}")

    def _emit_state(self):
        """Rozgłasza zmianę stanu do UI przez socketio."""
        if self._app is None:
            return
        try:
            from core.extensions import socketio
            with self._app.app_context():
                socketio.emit('replay_state_changed', {
                    'status': self.status,
                    'speed':  self.current_speed,
                })
        except Exception as e:
            try:
                self._app.logger.error(f"[controller] emit_state failed: {e}")
            except Exception:
                pass

    def _log(self, msg):
        if self._app is not None:
            try:
                self._app.logger.info(f"[controller] {msg}")
                return
            except Exception:
                pass
        print(f"[controller] {msg}")