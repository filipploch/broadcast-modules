"""Klient kanału sterującego HUB-a (127.0.0.1:<control_port>, hub/control.go). Własny krótki limit czasu (domyślnie 2 s),
niezależny od limitów HUB-a: zawieszony HUB nie może zawiesić okna managera. Każde żądanie to nowe połączenie (bez stanu po stronie HUB-a);
POST zawsze z Content-Type: application/json i bez nagłówka Origin (HUB odrzuca żądania ze stron w przeglądarce)."""
from __future__ import annotations

import http.client
import json
import socket

TIMEOUT_S = 2.0


class ChannelError(Exception):
    """kind: 'unreachable' (brak połączenia), 'timeout' (brak odpowiedzi w limicie), 'bad' (nieczytelna odpowiedź)."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


class Channel:
    def __init__(self, port: int, host: str = "127.0.0.1", timeout: float = TIMEOUT_S):
        self.host, self.port, self.timeout = host, port, timeout

    def _request(self, method, path, body=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            headers = {}
            data = None
            if method == "POST":
                data = json.dumps(body if body is not None else {}).encode()
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
        except (socket.timeout, TimeoutError) as e:
            raise ChannelError("timeout", f"HUB nie odpowiedział w {self.timeout:g} s") from e
        except (ConnectionError, OSError) as e:
            raise ChannelError("unreachable", f"brak połączenia z kanałem HUB-a (127.0.0.1:{self.port}): {e}") from e
        finally:
            conn.close()
        try:
            return resp.status, json.loads(raw.decode("utf-8") or "{}")
        except ValueError as e:
            raise ChannelError("bad", f"nieczytelna odpowiedź HUB-a ({resp.status})") from e

    def state(self) -> dict:
        code, data = self._request("GET", "/state")
        if code != 200:
            raise ChannelError("bad", f"/state: kod {code}")
        return data

    def recorder(self) -> dict:
        code, data = self._request("GET", "/recorder")
        if code != 200:
            raise ChannelError("bad", f"/recorder: kod {code}")
        return data

    def post(self, path: str, body=None):
        """Zwraca (kod, odpowiedź); odmowy HUB-a (409, 404, 415...) są zwykłą odpowiedzią z polem error."""
        return self._request("POST", path, body)
