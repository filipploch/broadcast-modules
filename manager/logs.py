"""Śledzenie pliku logu (zakładki HUB i Moduł). Manager czyta pliki, nie wyjście procesu: HUB działa bez okna i bez managera,
a zamknięcie managera niczego nie przerywa. Zmiana ścieżki (nowe uruchomienie HUB-a = nowy folder logów) zaczyna od początku nowego pliku."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


class Follower:
    def __init__(self):
        self.path: Optional[Path] = None
        self.pos = 0
        self._rest = b""

    def follow(self, path) -> list:
        """Zwraca nowe pełne wiersze z pliku od ostatniego odczytu."""
        if path is None:
            return []
        path = Path(path)
        if path != self.path:
            self.path, self.pos, self._rest = path, 0, b""
        try:
            size = path.stat().st_size
            if size < self.pos:  # plik przycięty (rotacja): od początku
                self.pos, self._rest = 0, b""
            with open(path, "rb") as f:
                f.seek(self.pos)
                data = f.read(1 << 20)
                self.pos = f.tell()
        except OSError:
            return []
        data = self._rest + data
        lines = data.split(b"\n")
        self._rest = lines.pop()
        return [l.decode("utf-8", "replace").rstrip("\r") for l in lines]


def module_log(state: Optional[dict]) -> Optional[Path]:
    """Log modułu bieżącego uruchomienia: modul-<log_name>.log w folderze logów HUB-a (moduł uruchomiony przez HUB pisze tam)."""
    if not state:
        return None
    log_dir = (state.get("hub") or {}).get("log_dir")
    active = state.get("active") or state.get("last_module") or {}
    name = active.get("name")
    if not name:
        mid = active.get("id")
        name = next((m.get("log_name") for m in state.get("modules", []) if m.get("id") == mid), None)
    if not log_dir or not name:
        return None
    return Path(log_dir) / f"modul-{name}.log"
