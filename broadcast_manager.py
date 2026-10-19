"""
Broadcast Manager — TUI do zarządzania OBS, HUB i modułami.

Uruchomienie:
    python broadcast_manager.py

Wymaga: pip install textual
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button, Footer, Header, Label, Log, Select, Static,
    TabbedContent, TabPane,
)

# ── Konfiguracja ──────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent

HUB_DIR = ROOT / "hub"
HUB_EXE = HUB_DIR / "hub.exe"

MODULES = {
    "garbarnia": ROOT / "modules" / "garbarnia.py",
    "nalf":      ROOT / "modules" / "nalf.py",
}

OBS_PATH = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"

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
    SUB_TITLE = "OBS · HUB · Moduły"

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

    Select { width: 100%; margin-bottom: 1; }

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
    TAB_MODULE = "modul"
    TAB_OBS    = "obs"

    def __init__(self):
        super().__init__()
        self._obs_proc:        Optional[subprocess.Popen] = None
        self._hub_proc:        Optional[subprocess.Popen] = None
        self._module_proc:     Optional[subprocess.Popen] = None
        self._selected_module: str = list(MODULES.keys())[0]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-layout"):
            with Vertical(id="controls"):
                yield Label("USŁUGI", classes="section-title")
                yield ServiceStatus("obs",    "OBS Studio", id="status-obs")
                yield ServiceStatus("hub",    "HUB",        id="status-hub")
                yield ServiceStatus("module", "Moduł",      id="status-module")

                yield Static("", classes="separator")
                yield Label("OBS", classes="section-title")
                yield Button("▶  Uruchom OBS",    id="btn-obs-start", classes="start")
                yield Button("■  Zatrzymaj OBS",   id="btn-obs-stop",  classes="stop")

                yield Static("", classes="separator")
                yield Label("HUB", classes="section-title")
                yield Button("▶  Uruchom HUB",    id="btn-hub-start", classes="start")
                yield Button("■  Zatrzymaj HUB",   id="btn-hub-stop",  classes="stop")

                yield Static("", classes="separator")
                yield Label("MODUŁ", classes="section-title")
                yield Select(
                    [(name, name) for name in MODULES],
                    value=self._selected_module,
                    id="module-select",
                )
                yield Button("▶  Uruchom moduł",  id="btn-mod-start", classes="start")
                yield Button("■  Zatrzymaj moduł", id="btn-mod-stop",  classes="stop")

                yield Static("", classes="separator")
                yield Label("DEBIAN", classes="section-title")
                yield Button("⏻  Wyłącz Debiana", id="btn-debian-off", classes="danger")

            with Vertical(id="log-panel"):
                with TabbedContent(initial=self.TAB_SYSTEM, id="tabs"):
                    with TabPane("System", id=self.TAB_SYSTEM):
                        yield Log(id="log-system", auto_scroll=True)
                    with TabPane("HUB",    id=self.TAB_HUB):
                        yield Log(id="log-hub",    auto_scroll=True)
                    with TabPane("Moduł",  id=self.TAB_MODULE):
                        yield Log(id="log-modul",  auto_scroll=True)
                    with TabPane("OBS",    id=self.TAB_OBS):
                        yield Log(id="log-obs",    auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#controls").border_title  = "Sterowanie"
        self.query_one("#log-panel").border_title = "Logi"
        self._log_sys("Broadcast Manager uruchomiony.")
        self._log_sys(f"ROOT: {ROOT}")
        self._log_sys(f"HUB:  {HUB_EXE}")
        for name, path in MODULES.items():
            self._log_sys(f"Moduł [{name}]: {path}")
        if not DEBIAN_SSH_HOST:
            self._log_sys("[UWAGA] Brak DEBIAN_SSH_HOST w .env")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        dispatch = {
            "btn-obs-start":  self._start_obs,
            "btn-obs-stop":   self._stop_obs,
            "btn-hub-start":  self._start_hub,
            "btn-hub-stop":   self._stop_hub,
            "btn-mod-start":  self._start_module,
            "btn-mod-stop":   self._stop_module,
            "btn-debian-off": self._shutdown_debian,
        }
        handler = dispatch.get(event.button.id)
        if handler:
            self.run_worker(handler(), exclusive=False)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "module-select":
            self._selected_module = str(event.value)
            self._log_sys(f"Wybrany moduł: {self._selected_module}")

    # ── OBS ───────────────────────────────────────────────────────────────────

    async def _start_obs(self) -> None:
        if self._obs_proc and self._obs_proc.poll() is None:
            self._log_sys("OBS już działa.")
            return
        obs_path = Path(OBS_PATH)
        if not obs_path.exists():
            self._log_sys(f"[BŁĄD] Nie znaleziono OBS: {obs_path}")
            return
        try:
            self._obs_proc = subprocess.Popen(
                [str(obs_path)],
                cwd=str(obs_path.parent),   # OBS szuka locale/ relatywnie do cwd
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            msg = f"OBS uruchomiony (pid {self._obs_proc.pid})"
            self._log_sys(msg)
            self._log_tab(self.TAB_OBS, msg)
            self._set_status("obs", True)
        except Exception as e:
            self._log_sys(f"[BŁĄD] OBS: {e}")

    async def _stop_obs(self) -> None:
        if not self._obs_proc or self._obs_proc.poll() is not None:
            self._log_sys("OBS nie działa.")
            self._set_status("obs", False)
            return
        self._obs_proc.terminate()
        self._log_sys("OBS zatrzymany.")
        self._log_tab(self.TAB_OBS, "OBS zatrzymany.")
        self._set_status("obs", False)

    # ── HUB ───────────────────────────────────────────────────────────────────

    async def _start_hub(self) -> None:
        if self._hub_proc and self._hub_proc.poll() is None:
            self._log_sys("HUB już działa.")
            return
        if not HUB_EXE.exists():
            self._log_sys(f"[BŁĄD] Nie znaleziono HUB: {HUB_EXE}")
            return
        try:
            self._hub_proc = subprocess.Popen(
                [str(HUB_EXE)],
                cwd=str(HUB_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
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
        self._hub_proc.terminate()
        await asyncio.sleep(0.5)
        if self._hub_proc.poll() is None:
            self._hub_proc.kill()
        self._log_sys("HUB zatrzymany.")
        self._set_status("hub", False)

    # ── Moduł ─────────────────────────────────────────────────────────────────

    async def _start_module(self) -> None:
        if self._module_proc and self._module_proc.poll() is None:
            self._log_sys(f"Moduł '{self._selected_module}' już działa.")
            return
        module_path = MODULES.get(self._selected_module)
        if not module_path or not module_path.exists():
            self._log_sys(f"[BŁĄD] Nie znaleziono modułu: {module_path}")
            return
        try:
            self._module_proc = subprocess.Popen(
                [sys.executable, str(module_path)],
                cwd=str(ROOT / "modules"),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._log_sys(
                f"Moduł '{self._selected_module}' uruchomiony "
                f"(pid {self._module_proc.pid})"
            )
            self._set_status("module", True)
            self.run_worker(
                self._tail(self._module_proc, self.TAB_MODULE, "module"),
                exclusive=False,
            )
        except Exception as e:
            self._log_sys(f"[BŁĄD] Moduł: {e}")

    async def _stop_module(self) -> None:
        if not self._module_proc or self._module_proc.poll() is not None:
            self._log_sys("Moduł nie działa.")
            self._set_status("module", False)
            return
        self._module_proc.terminate()
        await asyncio.sleep(1)
        if self._module_proc.poll() is None:
            self._module_proc.kill()
        self._log_sys(f"Moduł '{self._selected_module}' zatrzymany.")
        self._set_status("module", False)

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
        for proc, name in [
            (self._module_proc, "moduł"),
            (self._hub_proc,    "HUB"),
        ]:
            if proc and proc.poll() is None:
                self._log_sys(f"Zatrzymuję {name}...")
                proc.terminate()
        self.exit()


if __name__ == "__main__":
    BroadcastManager().run()