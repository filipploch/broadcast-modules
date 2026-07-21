"""HelperRelayClient — połączenie WSS modułu głównego z zewnętrzną apką
"pomocnika realizatora" hostowaną na Render (docs/helper-app-design.md).

Wzorowany na core.managers.hub_client.HubClient (ta sama koperta wiadomości
{from, to, type, payload, timestamp}, ta sama biblioteka websocket-client,
ten sam schemat auto-reconnect) — ale to POŁĄCZENIE WYCHODZĄCE DO INNEGO
SERWERA niż Hub, autentykowane tokenem, bo Render nie jest siecią lokalną.

Nie blokuje startu aplikacji: connect() startuje wątek w tle i wraca od
razu, nie czeka na potwierdzenie połączenia — Render może jeszcze nie
istnieć albo akurat spać (cold start), a to nie może wywalać main-module.
"""
import websocket
import json
import threading
import time
from datetime import datetime


class HelperRelayClient:

    def __init__(self, relay_url, token, app=None, ping_interval_s=300):
        self.relay_url = relay_url
        self.token = token
        self.app = app
        self.ping_interval_s = ping_interval_s
        self.ws = None
        self.connected = False
        self._lock = threading.Lock()
        self._should_reconnect = True
        self._reconnect_delay = 5
        self._ping_thread = None

    def connect(self):
        """Startuje połączenie w tle. Nie blokuje i nie rzuca wyjątków —
        brak działającego Render w danym momencie to normalny stan."""
        self._should_reconnect = True
        self._log("info", f"[helper-relay] Connecting to {self.relay_url}")
        threading.Thread(target=self._run_forever, daemon=True).start()
        if self._ping_thread is None:
            self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
            self._ping_thread.start()

    def _run_forever(self):
        attempt = 0
        while self._should_reconnect:
            try:
                self.ws = websocket.WebSocketApp(
                    self.relay_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open,
                )
                self.ws.run_forever()
            except Exception as e:
                self._log("error", f"[helper-relay] WebSocket error: {e}")

            if not self._should_reconnect:
                break
            attempt += 1
            self._log("info", f"[helper-relay] Reconnecting in {self._reconnect_delay}s (attempt {attempt})")
            time.sleep(self._reconnect_delay)

    def _ping_loop(self):
        """Ping podtrzymujący co ping_interval_s — patrz docs/helper-app-design.md sekcja 7."""
        while True:
            time.sleep(self.ping_interval_s)
            if self.connected:
                self.send({'from': 'main-module', 'to': 'relay', 'type': 'ping', 'payload': {}})

    def disconnect(self):
        self._should_reconnect = False
        self.connected = False
        if self.ws:
            self.ws.close()

    def send(self, message):
        if not self.connected:
            return False
        try:
            if 'timestamp' not in message:
                message['timestamp'] = datetime.utcnow().isoformat()
            with self._lock:
                self.ws.send(json.dumps(message))
            return True
        except Exception as e:
            self._log("error", f"[helper-relay] Failed to send message: {e}")
            return False

    def push(self, msg_type, payload):
        """Wyślij wiadomość do apki (period_state, event_recorded, ...)."""
        return self.send({'from': 'main-module', 'to': 'relay', 'type': msg_type, 'payload': payload})

    def _on_open(self, ws):
        self.connected = True
        self._log("info", "[helper-relay] Connected")
        self.send({
            'from': 'main-module', 'to': 'relay', 'type': 'register',
            'payload': {'token': self.token},
        })

    def _on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        self._log("warning", f"[helper-relay] Closed: {close_msg} (code: {close_status_code})")

    def _on_error(self, ws, error):
        self._log("error", f"[helper-relay] Error: {error}")

    def _on_message(self, ws, message):
        try:
            msg = json.loads(message)
        except Exception as e:
            self._log("error", f"[helper-relay] Bad message: {e}")
            return

        if self.app:
            with self.app.app_context():
                self._handle_message(msg)
        else:
            self._handle_message(msg)

    def _handle_message(self, msg):
        msg_type = msg.get('type')
        payload = msg.get('payload', {})

        if msg_type == 'helper_submission':
            from core.managers import get_helper_relay_manager
            get_helper_relay_manager().handle_incoming_submission(payload)
        elif msg_type == 'registered':
            self._log("info", "[helper-relay] Registered with relay")
        elif msg_type == 'pong':
            pass
        else:
            self._log("warning", f"[helper-relay] Unhandled message type: {msg_type}")

    def _log(self, level, message):
        if self.app:
            try:
                with self.app.app_context():
                    from flask import current_app
                    getattr(current_app.logger, level, current_app.logger.info)(message)
                    return
            except Exception:
                pass
        print(f"[{level.upper()}] {message}")
