"""
Broadcast Manager — TUI: uruchamia HUB, pokazuje jego logi i wyłącza Debiana.

Od E2d3a (okrojony): moduł główny i OBS uruchamia i nadzoruje HUB, więc przycisków startu OBS i modułu ani wyboru modułu
tu nie ma. Nazwa modułu jest tylko do odczytu, z konfiguracji HUB-a (hub/config/hub.json). Debiana budzi HUB przy starcie
(sekcja "wol" w hub.json). Decyzja o całkowitym usunięciu tego programu: po zakończeniu E2.

Uruchomienie:
    python broadcast_manager.py

Wymaga: pip install textual
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button, Footer, Header, Label, Log, Static,
    TabbedContent, TabPane,
)

from broadcast_manager_hub import hub_exe_stale, hub_module_choice, start_hub, stop_hub

# ── Konfiguracja ──────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent

HUB_DIR = ROOT / "hub"
HUB_EXE = HUB_DIR / "hub.exe"
HUB_CONFIG_DIR = HUB_DIR / "config"

def _load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env

_env = _load_env(ROOT / ".env")
DEBIAN_SSH_HOST = _env.get("DEBIAN_SSH_HOST", "")
DEBIAN_SSH_USER = _env.get("DEBIAN_SSH_USER", "")

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


class ServiceStatus(Static):
    running: reactive[bool] = reactive(False)

    def __init__(self, name: str, label: str, **kwargs):
        super().__init__(**kwargs)
        self._service_name = name
        self._label = label

    def render(self) -> str:
        dot   = "● " if self.running else "○ "
        state = "DZIAŁA    " if self.running else "zatrzymany"
        return f"{dot}{self._label:<16} {state}"

    def watch_running(self, value: bool) -> None:
        self.remove_class("running", "stopped")
        self.add_class("running" if value else "stopped")


class BroadcastManager(App):

    TITLE     = "Broadcast Manager"
    SUB_TITLE = "HUB · Debian"

    CSS = """
    Screen { background: #0d1117; }
    Header { background: #161b22; color: #58a6ff; text-style: bold; }
    Footer { background: #161b22; color: #8b949e; }

    #main-layout {
        layout: grid;
        grid-size: 2;
        grid-columns: 26 1fr;
        height: 1fr;

        padding: 1;
    }
    #controls {
        background: #161b22;
        border: solid #30363d;
        border-title-color: #58a6ff;
        border-title-style: bold;
        padding: 1;
        height: 100%;
        overflow-y: auto;
        margin-right: 1;
    }
    #log-panel {
        height: 100%;
        border: solid #30363d;
        border-title-color: #58a6ff;
        border-title-style: bold;
    }

    .section-title { color: #8b949e; text-style: bold; margin-top: 1; }
    .separator { height: 1; background: #21262d; margin: 1 0; }
    .info { color: #c9d1d9; }

    ServiceStatus       { height: 1; padding: 0; color: #f85149; }
    ServiceStatus.running { color: #3fb950; }
    ServiceStatus.stopped { color: #f85149; }

    Button              { width: 100%; margin-bottom: 1; }
    Button.start        { background: #196c2e; color: #fff; }
    Button.start:hover  { background: #238636; }
    Button.stop         { background: #3a1a1a; color: #f85149; }
    Button.stop:hover   { background: #6e1c21; }
    Button.danger       { background: #6e1c21; color: #ffa198; border: solid #f85149; }
    Button.danger:hover { background: #b62324; }

    TabbedContent { height: 1fr; }
    TabPane { padding: 0; height: 1fr; }
    Log {
        background: #0d1117;
        color: #c9d1d9;
        height: 1fr;
        padding: 0 1;
    }
    Tab.-active { color: #58a6ff; }
    """

    BINDINGS = [
        Binding("q",      "quit", "Wyjście", show=True),
        Binding("ctrl+c", "quit", "Wyjście", show=False),
    ]

    TAB_SYSTEM = "system"
    TAB_HUB    = "hub"

    def __init__(self):
        super().__init__()
        self._hub_proc: Optional[subprocess.Popen] = None
        self._module_name, self._module_source = hub_module_choice(HUB_CONFIG_DIR)

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-layout"):
            with Vertical(id="controls"):
                yield Label("HUB", classes="section-title")
                yield ServiceStatus("hub", "HUB", id="status-hub")
                yield Static(f"Moduł: {self._module_name or '(brak)'}", id="module-name", classes="info")
                yield Button("▶  Uruchom HUB",    id="btn-hub-start", classes="start")
                yield Button("■  Zatrzymaj HUB",   id="btn-hub-stop",  classes="stop")

                yield Static("", classes="separator")
                yield Label("DEBIAN", classes="section-title")
                yield Button("⏻  Wyłącz Debiana", id="btn-debian-off", classes="danger")

            with Vertical(id="log-panel"):
                with TabbedContent(initial=self.TAB_SYSTEM, id="tabs"):
                    with TabPane("System", id=self.TAB_SYSTEM):
                        yield Log(id="log-system", auto_scroll=True)
                    # Konsola HUB-a pokazuje też wiersze modułu (prefiks [moduł]) i pluginów lokalnych
                    with TabPane("HUB",    id=self.TAB_HUB):
                        yield Log(id="log-hub",    auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#controls").border_title  = "Sterowanie"
        self.query_one("#log-panel").border_title = "Logi"
        self._log_sys("Broadcast Manager uruchomiony.")
        self._log_sys(f"ROOT: {ROOT}")
        self._log_sys(f"HUB:  {HUB_EXE}")
        self._log_sys(f"Moduł uruchamiany przez HUB: {self._module_name or '(brak)'} (źródło: {self._module_source})")
        self._log_sys("Moduł, OBS i budzenie Debiana obsługuje HUB; zmiana modułu: pole \"module\" w hub/config/hub.json.")
        stale = hub_exe_stale(HUB_EXE, HUB_DIR)
        if stale:
            self._log_sys(f"[UWAGA] {stale}")
        if not DEBIAN_SSH_HOST:
            self._log_sys("[UWAGA] Brak DEBIAN_SSH_HOST w .env")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        dispatch = {
            "btn-hub-start":  self._start_hub,
            "btn-hub-stop":   self._stop_hub,
            "btn-debian-off": self._shutdown_debian,
        }
        handler = dispatch.get(event.button.id)
        if handler:
            self.run_worker(handler(), exclusive=False)

    # ── HUB ───────────────────────────────────────────────────────────────────

    async def _start_hub(self) -> None:
        if self._hub_proc and self._hub_proc.poll() is None:
            self._log_sys("HUB już działa.")
            return
        if not HUB_EXE.exists():
            self._log_sys(f"[BŁĄD] Nie znaleziono HUB: {HUB_EXE}")
            return
        stale = hub_exe_stale(HUB_EXE, HUB_DIR)
        if stale:
            self._log_sys(f"[UWAGA] {stale}")
        try:
            self._hub_proc = start_hub(HUB_EXE, HUB_DIR)
            self._log_sys(f"HUB uruchomiony (pid {self._hub_proc.pid})")
            self._set_status("hub", True)
            self.run_worker(
                self._tail(self._hub_proc, self.TAB_HUB, "hub"),
                exclusive=False,
            )
        except Exception as e:
            self._log_sys(f"[BŁĄD] HUB: {e}")

    async def _stop_hub(self) -> None:
        if not self._hub_proc or self._hub_proc.poll() is not None:
            self._log_sys("HUB nie działa.")
            self._set_status("hub", False)
            return
        rc = await asyncio.get_event_loop().run_in_executor(None, stop_hub, self._hub_proc, self._log_sys)
        self._log_sys(f"HUB zatrzymany (kod {rc}).")
        self._set_status("hub", False)

    # ── Debian ────────────────────────────────────────────────────────────────

    async def _shutdown_debian(self) -> None:
        if not DEBIAN_SSH_HOST or not DEBIAN_SSH_USER:
            self._log_sys("[BŁĄD] Brak DEBIAN_SSH_HOST / DEBIAN_SSH_USER w .env")
            return
        self._log_sys(f"Wysyłam shutdown → {DEBIAN_SSH_USER}@{DEBIAN_SSH_HOST}...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=5",
                f"{DEBIAN_SSH_USER}@{DEBIAN_SSH_HOST}",
                "sudo shutdown -h now",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if stdout:
                self._log_sys(f"[SSH] {stdout.decode().strip()}")
            if proc.returncode == 0:
                self._log_sys("✓ Debian wyłącza się.")
            else:
                self._log_sys(f"[BŁĄD] SSH kod {proc.returncode}")
        except asyncio.TimeoutError:
            self._log_sys("[BŁĄD] SSH timeout — brak połączenia?")
        except FileNotFoundError:
            self._log_sys("[BŁĄD] Nie znaleziono 'ssh'. Zainstaluj OpenSSH.")
        except Exception as e:
            self._log_sys(f"[BŁĄD] SSH: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_sys(self, msg: str) -> None:
        self._log_tab(self.TAB_SYSTEM, msg)

    def _log_tab(self, tab_id: str, msg: str) -> None:
        try:
            self.query_one(f"#log-{tab_id}", Log).write_line(f"{_now()}  {msg}")
        except Exception:
            pass

    async def _tail(
        self,
        proc: subprocess.Popen,
        tab_id: str,
        service_key: str,
    ) -> None:
        if proc.stdout is None:
            return
        loop = asyncio.get_event_loop()
        try:
            while True:
                line = await loop.run_in_executor(None, proc.stdout.readline)
                if not line:
                    break
                self._log_tab(tab_id, line.rstrip())
        except Exception:
            pass
        rc = proc.poll()
        self._log_tab(tab_id, f"--- Proces zakończony (kod {rc}) ---")
        self._log_sys(f"[{tab_id.upper()}] Proces zakończony (kod {rc})")
        self._set_status(service_key, False)

    def _set_status(self, service: str, running: bool) -> None:
        try:
            self.query_one(f"#status-{service}", ServiceStatus).running = running
        except Exception:
            pass

    async def action_quit(self) -> None:
        # Wyjście zamyka HUB łagodnie (jak przycisk); moduł i OBS zamyka albo zostawia sam HUB według reguł z E2d2
        if self._hub_proc and self._hub_proc.poll() is None:
            self._log_sys("Zatrzymuję HUB przed wyjściem...")
            await asyncio.get_event_loop().run_in_executor(None, stop_hub, self._hub_proc, self._log_sys)
        self.exit()


if __name__ == "__main__":
    BroadcastManager().run()
