"""
Broadcast Manager — panel HUB-a (E2d3c2): przyciski modułów z plików module.json, zatrzymanie HUB-a, Debian.

Uruchomienie:
    modules\\.venv\\Scripts\\python.exe broadcast_manager.py [--config hub.json]

Wymaga: modules\\.venv\\Scripts\\python.exe -m pip install -r modules\\requirements-manager.txt  (textual==8.2.3)

Okno jest tylko panelem: HUB startuje razem z managerem (albo manager podłącza się do działającego), moduł uruchamia HUB na prośbę
z kanału sterującego, a zamknięcie okna nie zatrzymuje HUB-a ani usług. Cała logika jest w pakiecie manager/ (bez textual).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

INSTALL_HINT = ("Brak biblioteki textual w tym środowisku Pythona (potrzebna do okna managera).\n"
                "Zainstaluj ją poleceniem (w katalogu głównym folderu):\n"
                "    modules\\.venv\\Scripts\\python.exe -m pip install -r modules\\requirements-manager.txt\n"
                "a potem uruchom manager ponownie:  modules\\.venv\\Scripts\\python.exe broadcast_manager.py")

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Footer, Header, Label, Log, Static, TabbedContent, TabPane
except ImportError:
    print(INSTALL_HINT, file=sys.stderr)
    sys.exit(1)

from manager import catalog, config as mconfig, debian, logs as mlogs, view as mview
from manager.channel import ChannelError
from manager.hub_process import Supervisor

ROOT = Path(__file__).resolve().parent
HUB_EXE = ROOT / "hub" / "hub.exe"


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


class Confirm(ModalScreen[bool]):
    """Okno potwierdzenia: tekst i ostrzeżenia, przyciski Tak / Anuluj."""

    def __init__(self, title: str, lines: list, yes: str = "Tak"):
        super().__init__()
        self._title, self._lines, self._yes = title, lines, yes

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title, id="dialog-title")
            for line in self._lines:
                yield Label("⚠  " + line, classes="dialog-warning")
            with Horizontal(id="dialog-buttons"):
                yield Button(self._yes, id="yes", classes="danger")
                yield Button("Anuluj", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class BroadcastManager(App):

    TITLE = "Broadcast Manager"
    SUB_TITLE = "HUB · moduły · Debian"

    CSS = """
    Screen { background: #0d1117; }
    Header { background: #161b22; color: #58a6ff; text-style: bold; }
    Footer { background: #161b22; color: #8b949e; }
    #main-layout { layout: grid; grid-size: 2; grid-columns: 34 1fr; height: 1fr; padding: 1; }
    #controls { background: #161b22; border: solid #30363d; border-title-color: #58a6ff; border-title-style: bold;
                padding: 1; height: 100%; overflow-y: auto; margin-right: 1; }
    #right { height: 100%; }
    #banners { height: auto; max-height: 8; padding: 0 1; }
    #module-buttons { height: auto; }  /* wysokość według liczby przycisków (domyślne 1fr ucinało drugi przycisk przy niskim oknie) */
    #log-panel { height: 1fr; border: solid #30363d; border-title-color: #58a6ff; border-title-style: bold; }
    .section-title { color: #8b949e; text-style: bold; margin-top: 1; }
    .separator { height: 1; background: #21262d; margin: 1 0; }
    .status { color: #c9d1d9; }
    Button { width: 100%; margin-bottom: 1; }
    Button.green { background: #196c2e; color: #fff; }
    Button.red { background: #8b1a1a; color: #fff; }
    Button.grey { background: #30363d; color: #8b949e; }
    Button.danger { background: #6e1c21; color: #ffa198; border: solid #f85149; }
    TabbedContent { height: 1fr; }
    TabPane { padding: 0; height: 1fr; }
    Log { background: #0d1117; color: #c9d1d9; height: 1fr; padding: 0 1; }
    #dialog { width: 70; height: auto; padding: 1 2; background: #161b22; border: thick #f85149; }
    #dialog-title { text-style: bold; margin-bottom: 1; }
    .dialog-warning { color: #ffa198; }
    #dialog-buttons { height: auto; margin-top: 1; }
    #dialog-buttons Button { width: 1fr; margin: 0 1; }
    ModalScreen { align: center middle; }
    """

    BINDINGS = [Binding("q", "quit", "Wyjście (HUB działa dalej)", show=True), Binding("ctrl+c", "quit", "Wyjście", show=False)]

    def __init__(self, config_path=None):
        super().__init__()
        self.cfg = mconfig.load(config_path)
        self.sup = Supervisor(self.cfg, HUB_EXE)
        self.catalog = catalog.scan(self.cfg.modules_dir)
        self.view = mview.View()
        self.debian_state = "no_host" if not DEBIAN_SSH_HOST else "unreachable"
        self.hub_follow, self.mod_follow, self.out_follow = mlogs.Follower(), mlogs.Follower(), mlogs.Follower()
        self._button_ids: list = []
        self._busy = False

    # ── wygląd ──

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-layout"):
            with Vertical(id="controls"):
                yield Label("HUB", classes="section-title")
                yield Static("HUB: sprawdzam…", id="hub-status", classes="status")
                yield Label("MODUŁY", classes="section-title")
                yield Vertical(id="module-buttons")
                yield Static("", classes="separator")
                yield Button("HUB: sprawdzam…", id="btn-hub", classes="grey", disabled=True)
                yield Static("", classes="separator")
                yield Label("DEBIAN", classes="section-title")
                yield Static("Debian: sprawdzam…", id="debian-status", classes="status")
                yield Button("⏻  Wyłącz Debiana", id="btn-debian-off", classes="danger", disabled=True)
            with Vertical(id="right"):
                yield Static("", id="banners")
                with Vertical(id="log-panel"):
                    with TabbedContent(initial="tab-system", id="tabs"):
                        with TabPane("System", id="tab-system"):
                            yield Log(id="log-system", auto_scroll=True)
                        with TabPane("HUB", id="tab-hub"):
                            yield Log(id="log-hub", auto_scroll=True)
                        with TabPane("Moduł", id="tab-modul"):
                            yield Log(id="log-modul", auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#controls").border_title = "Sterowanie"
        self.query_one("#log-panel").border_title = "Logi"
        self._log_sys(f"Broadcast Manager uruchomiony. Konfiguracja HUB-a: {self.cfg.source}, kanał 127.0.0.1:{self.cfg.control_port}")
        if self.cfg.error:
            self._log_sys(f"[BŁĄD] {self.cfg.error}")
        if not DEBIAN_SSH_HOST:
            self._log_sys("[UWAGA] Brak DEBIAN_SSH_HOST w .env (stan Debiana: brak adresu)")
        self.set_interval(1.0, self._tick)
        self.set_interval(5.0, self._ping)
        self._tick()
        self._ping()

    # ── cykl: nadzór i odświeżenie (w wątku: kanał ma limit 2 s, okno nie może czekać) ──

    def _tick(self) -> None:
        if not self._busy:
            self._busy = True
            self.run_worker(self._tick_thread, thread=True, exclusive=False)

    def _tick_thread(self) -> None:
        try:
            self.sup.tick()
            cat = catalog.scan(self.cfg.modules_dir)
            phase = mview.hub_phase(self.sup.phase == "ok", self.sup.seconds_since_start(), self.sup.phase)
            v = mview.build(cat, self.sup.state, phase, root=ROOT, supervising=self.sup.supervising)
            events = list(self.sup.events)
            self.sup.events.clear()
            hub_lines = self.hub_follow.follow(((self.sup.state or {}).get("hub") or {}).get("hub_log"))
            mod_lines = self.mod_follow.follow(mlogs.module_log(self.sup.state))
            mod_lines += ["[wyjście] " + l for l in self.out_follow.follow(mlogs.module_output_log(self.sup.state)) if l.strip()]
            self.call_from_thread(self._apply, cat, v, events, hub_lines, mod_lines)
        finally:
            self._busy = False

    def _apply(self, cat, v, events, hub_lines, mod_lines) -> None:
        self.catalog, self.view = cat, v
        for e in events:
            self._log_sys(f"[{e.kind}] {e.text}")
        for line in hub_lines:
            self.query_one("#log-hub", Log).write_line(line)
        for line in mod_lines:
            self.query_one("#log-modul", Log).write_line(line)
        self.query_one("#hub-status", Static).update(f"HUB: {v.hub_text}" + ("" if self.sup.supervising else " (nadzoruje inny manager)"))
        colors = {"info": "#8b949e", "warn": "#d29922", "error": "#f85149"}
        self.query_one("#banners", Static).update("\n".join(f"[{colors[b.level]}]{b.text}[/]" for b in v.banners))
        self._sync_buttons(v.buttons)
        hb = v.hub_button
        w = self.query_one("#btn-hub", Button)
        w.label, w.disabled, w.hub_action = hb.text, not hb.enabled, hb.action
        w.set_classes(hb.color)

    def _sync_buttons(self, buttons) -> None:
        box = self.query_one("#module-buttons", Vertical)
        ids = [f"mod-{i}-{b.id or 'reczny'}" for i, b in enumerate(buttons)]
        if ids != self._button_ids:
            box.remove_children()
            box.mount_all([Button(b.text, id=wid) for wid, b in zip(ids, buttons)])
            self._button_ids = ids
        for wid, b in zip(ids, buttons):
            w = self.query_one(f"#{wid}", Button)
            w.label = b.text
            w.disabled = not b.enabled
            w.set_classes(b.color)
            w.mod_action, w.mod_id = b.action, b.id

    # ── Debian ──

    def _ping(self) -> None:
        self.run_worker(self._ping_thread, thread=True, exclusive=False)

    def _ping_thread(self) -> None:
        st = debian.ping(DEBIAN_SSH_HOST)
        self.call_from_thread(self._apply_ping, st)

    def _apply_ping(self, st) -> None:
        if st != self.debian_state:
            self._log_sys(f"Debian: {debian.LABELS[st]}")
        self.debian_state = st
        self.query_one("#debian-status", Static).update(f"Debian: {debian.LABELS[st]}")
        self.query_one("#btn-debian-off", Button).disabled = st != "up"

    # ── przyciski ──

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("mod-"):
            action, mid = getattr(event.button, "mod_action", ""), getattr(event.button, "mod_id", "")
            if action:
                self.run_worker(lambda: self._module_action(action, mid), thread=True)
        elif bid == "btn-hub" and getattr(event.button, "hub_action", "") == "stop_hub":
            self.push_screen(Confirm("Zatrzymać HUB?", ["Moduł, OBS i pluginy zostaną zamknięte według reguł HUB-a.",
                                                          "Manager nie uruchomi HUB-a ponownie, dopóki nie klikniesz \"URUCHOM HUB\"."],
                                     yes="Zatrzymaj HUB"), self._stop_hub_confirmed)
        elif bid == "btn-hub" and getattr(event.button, "hub_action", "") == "start_hub":
            self.run_worker(self._start_hub, thread=True)
        elif bid == "btn-debian-off":
            self.run_worker(self._debian_prepare, thread=True)

    def _module_action(self, action, mid) -> None:
        path, body = ("/module/start", {"id": mid}) if action == "start" else ("/module/stop", {})
        try:
            code, res = self.sup.channel.post(path, body)
            msg = "przyjęte" if code == 202 else (res.get("error") or f"kod {code}")
        except ChannelError as e:
            msg = str(e)
        what = f"Uruchomienie modułu {mid}" if action == "start" else "Zatrzymanie modułu"
        self.call_from_thread(self._log_sys, f"{what}: {msg}")
        if action == "stop" and msg != "przyjęte":
            self.call_from_thread(self.notify, msg, severity="warning", timeout=8)

    def _stop_hub_confirmed(self, yes) -> None:
        if yes:
            self.run_worker(self._stop_hub, thread=True)

    def _stop_hub(self) -> None:
        ok, msg = self.sup.stop_hub()
        self.call_from_thread(self._log_sys, f"ZATRZYMAJ HUB: {msg}")
        if not ok:
            self.call_from_thread(self.notify, msg, severity="warning", timeout=8)

    def _start_hub(self) -> None:
        if not HUB_EXE.exists():
            self.call_from_thread(self._log_sys, f"[BŁĄD] Nie znaleziono {HUB_EXE} (zbuduj: hub\\build.bat)")
            return
        pid = self.sup.start(by_user=True)
        self.call_from_thread(self._log_sys, f"Uruchomiono HUB (PID {pid})")

    def _debian_prepare(self) -> None:
        try:
            rec = self.sup.channel.recorder().get("state", "unknown")
        except ChannelError:
            rec = "hub_unreachable"
        session = (self.sup.state or {}).get("session") or {}
        v = debian.confirm_variant(rec, session.get("open"), bool(session.get("known")))
        self.call_from_thread(self._debian_confirm, v)

    def _debian_confirm(self, v) -> None:
        def second(yes):
            if yes and v.confirmations == 2:
                self.push_screen(Confirm("Na pewno wyłączyć Debiana mimo ostrzeżeń?", v.warnings, yes="Tak, wyłącz"), final)
            elif yes:
                final(True)

        def final(yes):
            if yes:
                self.run_worker(self._debian_shutdown, thread=True)

        self.push_screen(Confirm("Wyłączyć komputer z recorder-pluginem (Debian)?", v.warnings, yes="Wyłącz Debiana"), second)

    def _debian_shutdown(self) -> None:
        ok, msg = debian.shutdown(DEBIAN_SSH_HOST, DEBIAN_SSH_USER)
        self.call_from_thread(self._log_sys, ("✓ " if ok else "[BŁĄD] ") + msg)

    # ── pomocnicze ──

    def _log_sys(self, msg: str) -> None:
        try:
            self.query_one("#log-system", Log).write_line(f"{_now()}  {msg}")
        except Exception:
            pass

    async def action_quit(self) -> None:
        # Zamknięcie okna niczego nie zatrzymuje: HUB, moduł, OBS i pluginy działają dalej (nadzór przejmie kolejny manager)
        self.sup.close()
        self.exit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="plik konfiguracji HUB-a (próby); domyślnie hub/config/hub.json")
    BroadcastManager(ap.parse_args().config).run()
