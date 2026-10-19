"""
Pomocnicze funkcje okrojonego broadcast_manager.py (E2d3a), bez zależności od textual (testowalne osobno).

- hub_module_choice: który moduł uruchomi HUB i skąd to wiadomo (ta sama kolejność co w HUB-ie: hub.json, hub.example.json,
  wartość wbudowana). Tylko do odczytu: wyboru modułu dokonuje się w hub/config/hub.json (wybór w interfejsie wraca w E2h).
- start_hub / stop_hub: HUB we własnej grupie procesów, zatrzymywany łagodnie sygnałem CTRL_BREAK (dla HUB-a to to samo co Ctrl+C
  w jego oknie: zamyka usługi według reguł z E2d2, przy otwartej sesji moduł i OBS zostają). Wymuszenie dopiero po limicie czasu.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

BUILTIN_MODULE = "nalf"  # jak defaultHubConfig() w hub/config.go
HUB_STOP_GRACE_S = 60    # HUB zamyka moduł (do 10 s) i OBS (do 30 s), więc dajemy mu zapas


def hub_module_choice(config_dir: Path) -> tuple[str, str]:
    """Zwraca (nazwa modułu, źródło). Pusta nazwa: HUB nie uruchamia modułu. Plik uszkodzony: nazwa '?' i opis błędu
    (HUB z takim plikiem nie wystartuje)."""
    for name in ("hub.json", "hub.example.json"):
        path = config_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            return "?", f"{name} uszkodzony ({e}); HUB nie wystartuje"
        source = name if name == "hub.json" else "hub.example.json (brak hub.json)"
        return str(data.get("module", BUILTIN_MODULE)), source
    return BUILTIN_MODULE, "wartości wbudowane (brak hub.json i hub.example.json)"


def hub_exe_stale(hub_exe: Path, src_dir: Path) -> Optional[str]:
    """Ostrzeżenie, gdy hub.exe jest starszy niż najnowszy plik źródłowy HUB-a (*.go w hub/). Manager uruchamia gotowy plik
    i niczego nie buduje, więc bez przebudowania działa stara wersja HUB-a (zgłoszone w próbie E2d3a, 2026-10-19).
    None: plik aktualny albo nie da się porównać (brak hub.exe lub źródeł, np. w folderze bez kodu Go)."""
    try:
        exe_mtime = hub_exe.stat().st_mtime
        sources = [p for p in src_dir.glob("*.go") if not p.name.endswith("_test.go")]
        if not sources:
            return None
        newest = max(sources, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
    if newest.stat().st_mtime <= exe_mtime:
        return None
    fmt = "%Y-%m-%d %H:%M"
    return (f"hub.exe ({time.strftime(fmt, time.localtime(exe_mtime))}) jest starszy niż źródło {newest.name} "
            f"({time.strftime(fmt, time.localtime(newest.stat().st_mtime))}): uruchomi się stara wersja HUB-a. "
            f"Przebuduj: w folderze hub polecenie  go build -o hub.exe .")


def start_hub(hub_exe: Path, cwd: Path) -> subprocess.Popen:
    """Uruchamia HUB z wyjściem do potoku (zakładka logów) we własnej grupie procesów, żeby dało się wysłać mu CTRL_BREAK."""
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    return subprocess.Popen(
        [str(hub_exe)],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=flags,
    )


def stop_hub(proc: subprocess.Popen, log: Callable[[str], None], grace_s: float = HUB_STOP_GRACE_S) -> Optional[int]:
    """Łagodne zatrzymanie HUB-a; po grace_s sekundach wymuszenie (HUB-a, nie OBS ani modułu: to osobne procesy odłączone).
    Zwraca kod wyjścia albo None, gdy proces już nie działał."""
    if proc.poll() is not None:
        return None
    try:
        if sys.platform == "win32":
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        else:
            proc.send_signal(signal.SIGINT)
    except OSError as e:
        log(f"[BŁĄD] Nie udało się wysłać HUB-owi prośby o zamknięcie: {e}")
    log(f"Zamykanie HUB-a (czekam do {grace_s:g} s; przy otwartej sesji moduł i OBS zostają)...")
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return proc.returncode
        time.sleep(0.2)
    log(f"[UWAGA] HUB nie zamknął się w {grace_s:g} s: kończę go z wymuszeniem (moduł i OBS działają dalej; następny HUB je przejmie)")
    proc.kill()
    return proc.wait(timeout=10)
