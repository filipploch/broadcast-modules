"""Nadzór procesu HUB-a przez manager (E2d3c2).

Zasady:
  - Tylko JEDEN manager nadzoruje i restartuje HUB (blokada pliku manager-nadzor.lock w folderze run/); kolejny manager tylko
    pokazuje stan i się podłącza, a nadzór przejmuje, gdy pierwszy się zamknie.
  - Start managera: HUB już odpowiada -> podłączenie; nie odpowiada -> nadzorca uruchamia hub.exe --module none jako proces odłączony
    (bez okna; zamknięcie managera nie zatrzymuje HUB-a ani usług). Wyjątek: znacznik "zatrzymany celowo".
  - Restart wyłącznie po awarii: proces HUB-a zniknął bez polecenia z managera i zakończył się kodem innym niż 0; najwyżej 3 z rzędu,
    licznik zerowany po 5 minutach stabilnej pracy. Kod 0 (np. Ctrl+C) = bez restartu.
  - Po przyjętym POST /hub/stop zapisywany jest znacznik manager-hub-zatrzymany.json: żaden kod wyjścia nie daje wtedy restartu, a drugi
    manager (otwarty przy działającym pierwszym) i przejmujący nadzór go respektują. Wariant A (decyzja właściciela): znacznik chroni tylko,
    dopóki działa jakiś manager albo HUB; świeży start managera, gdy nie działa żaden inny manager ani HUB, kasuje go i uruchamia HUB
    (HUB startuje razem z managerem). Znacznik kasuje też przycisk "Uruchom HUB".
  - Proces HUB-a przejmowany po numerze z /state tylko przy zgodnym czasie utworzenia procesu: zapis managera, który go uruchomił
    (manager-hub.json), albo czas pracy z /state (tolerancja 5 s). Niezgodny = nie ten proces: reguła kodu wyjścia nie jest stosowana.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .channel import Channel, ChannelError

MAX_RESTARTS = 3
STABLE_AFTER_S = 300
CREATED_TOLERANCE_S = 5
LOCK_NAME = "manager-nadzor.lock"
MARKER_NAME = "manager-hub-zatrzymany.json"
RECORD_NAME = "manager-hub.json"

# --- proces po numerze (Windows) ---

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_STILL_ACTIVE = 259
_EPOCH_AS_FILETIME = 116444736000000000

if sys.platform == "win32":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]


class ProcHandle:
    """Uchwyt procesu: czas utworzenia i kod wyjścia (także procesu, którego manager nie uruchomił)."""

    def __init__(self, pid: int, handle):
        self.pid, self._h = pid, handle

    @classmethod
    def open(cls, pid: int) -> Optional["ProcHandle"]:
        if sys.platform != "win32" or not pid:
            return None
        h = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, False, pid)
        return cls(pid, h) if h else None

    def created_ft(self) -> int:
        c, e, k, u = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        if not _k32.GetProcessTimes(self._h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return 0
        return (c.dwHighDateTime << 32) | c.dwLowDateTime

    def created_unix(self) -> float:
        return (self.created_ft() - _EPOCH_AS_FILETIME) / 1e7

    def exit_code(self) -> Optional[int]:
        """None, gdy proces działa."""
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(self._h, ctypes.byref(code)):
            return None
        return None if code.value == _STILL_ACTIVE else int(code.value)

    def close(self):
        if self._h:
            _k32.CloseHandle(self._h)
            self._h = None


# --- pliki managera ---

class StopMarker:
    """Znacznik "HUB zatrzymany celowo" (po przyjętym POST /hub/stop). Plik, więc respektują go inne managery i ponowne otwarcie."""

    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / MARKER_NAME

    def set(self, pid: int):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"pid": pid, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")

    def clear(self):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def active(self) -> bool:
        return self.path.exists()


class SupervisorLock:
    """Blokada nadzoru: plik zablokowany przez proces managera-nadzorcy (zwalniana przez system także po awarii managera)."""

    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / LOCK_NAME
        self._f = None

    def acquire(self) -> bool:
        if self._f is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = open(self.path, "a+")
        try:
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            f.close()
            return False
        f.seek(0)
        f.truncate()
        f.write(str(os.getpid()))
        f.flush()
        self._f = f
        return True

    def release(self):
        if self._f is not None:
            try:
                import msvcrt
                self._f.seek(0)
                msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            self._f.close()
            self._f = None

    @property
    def held(self) -> bool:
        return self._f is not None


class LaunchRecord:
    """Numer i czas utworzenia HUB-a uruchomionego przez manager (do rozpoznania przy podłączeniu)."""

    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / RECORD_NAME

    def save(self, pid: int, created_ft: int):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"pid": pid, "created_ft": created_ft}), encoding="utf-8")

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


# --- polityka restartów ---

class RestartPolicy:
    def __init__(self, max_restarts=MAX_RESTARTS, stable_after_s=STABLE_AFTER_S):
        self.max, self.stable = max_restarts, stable_after_s
        self.count = 0
        self.last_start = None

    def note_start(self, now: float):
        self.last_start = now

    def allow_restart(self, now: float) -> bool:
        if self.last_start is not None and now - self.last_start >= self.stable:
            self.count = 0
        if self.count >= self.max:
            return False
        self.count += 1
        return True

    def reset(self):
        self.count = 0


# --- uruchamianie HUB-a ---

def launch_hub(hub_exe: Path, config_path: Optional[Path]) -> int:
    """Uruchamia hub.exe --module none jako proces odłączony (bez okna i bez wspólnej konsoli). Zwraca numer procesu."""
    args = [str(hub_exe), "--module", "none"]
    if config_path is not None:
        args += ["--config", str(config_path)]
    cwd = hub_exe.parent / "hub" if (hub_exe.parent / "hub").is_dir() else hub_exe.parent
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    pr = subprocess.Popen(args, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          creationflags=flags, close_fds=True)
    return pr.pid


@dataclass
class Event:
    kind: str   # started, attached, restarted, gave_up, stopped, exited, not_same_process, observer
    text: str


class Supervisor:
    """Stan HUB-a widziany przez manager i decyzje nadzorcy. tick() woła okno (co sekundę) albo nadzór bez okna (próby M5-M6)."""

    def __init__(self, cfg, hub_exe: Path, channel: Optional[Channel] = None, clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time, launcher=None, open_proc=ProcHandle.open):
        self.cfg, self.hub_exe = cfg, Path(hub_exe)
        self.channel = channel or Channel(cfg.control_port)
        self.clock, self.wall = clock, wall
        self.launcher = launcher or (lambda: launch_hub(self.hub_exe, cfg.config_path if cfg.explicit else None))
        self.open_proc = open_proc
        self.lock = SupervisorLock(cfg.run_dir)
        self.marker = StopMarker(cfg.run_dir)
        self.record = LaunchRecord(cfg.run_dir)
        self.policy = RestartPolicy()
        self.proc: Optional[ProcHandle] = None
        self.phase = "not_started"
        self.state: Optional[dict] = None
        self.started_at: Optional[float] = None
        self.events: list = []
        self._first = True
        self._mu = threading.RLock()  # okno woła nadzór z kilku wątków (odświeżanie, przyciski)
        self._closed = False

    @property
    def supervising(self) -> bool:
        return self.lock.held

    def _event(self, kind, text):
        self.events.append(Event(kind, text))

    def seconds_since_start(self):
        return None if self.started_at is None else self.clock() - self.started_at

    # -- start i zatrzymanie --

    def start(self, by_user=False):
        with self._mu:
            return self._start(by_user)

    def _start(self, by_user=False):
        if by_user:
            self.marker.clear()
            self.policy.reset()
        pid = self.launcher()
        now = self.clock()
        self.started_at = now
        self.policy.note_start(now)
        h = self.open_proc(pid)
        if h is not None:
            self.record.save(pid, h.created_ft())
        self._set_proc(h)
        self.phase = "starting"
        return pid

    def stop_hub(self):
        with self._mu:
            return self._stop_hub()

    def _stop_hub(self):
        """POST /hub/stop. Zwraca (ok, komunikat). Po przyjęciu: znacznik "zatrzymany celowo" (bez restartu przy żadnym kodzie wyjścia)."""
        pid = ((self.state or {}).get("hub") or {}).get("pid", 0)
        try:
            code, res = self.channel.post("/hub/stop", {})
        except ChannelError as e:
            return False, str(e)
        if code == 202:
            self.marker.set(pid)
            self._event("stopped", "HUB zatrzymany celowo (bez automatycznego restartu)")
            return True, "HUB się zamyka"
        return False, res.get("error") or f"odmowa HUB-a ({code})"

    def _set_proc(self, h):
        if self.proc is not None and self.proc is not h:
            self.proc.close()
        self.proc = h

    # -- tożsamość procesu z /state --

    def _attach(self, st: dict):
        hub = st.get("hub") or {}
        pid = hub.get("pid") or 0
        if self.proc is not None and self.proc.pid == pid:
            return
        h = self.open_proc(pid)
        if h is None:
            self._set_proc(None)
            return
        rec = self.record.load()
        created = h.created_ft()
        if rec.get("pid") == pid:
            same = rec.get("created_ft") == created
        else:
            expected = self.wall() - float(hub.get("uptime_s", 0))
            same = abs(h.created_unix() - expected) <= CREATED_TOLERANCE_S
        if not same:
            h.close()
            self._set_proc(None)
            self._event("not_same_process", f"proces {pid} ma inny czas utworzenia niż HUB z /state: nie przejmuję go (bez reguły kodu wyjścia)")
            return
        self._set_proc(h)
        self._event("attached", f"podłączono do HUB-a (PID {pid})")

    # -- jeden krok nadzoru --

    def tick(self):
        with self._mu:
            if not self._closed:  # po zamknięciu okna odświeżanie w tle nie zajmuje ponownie blokady nadzoru
                self._tick()

    def _tick(self):
        if not self.lock.held and self.lock.acquire() and not self._first:
            self._event("observer", "ten manager przejął nadzór HUB-a")
        try:
            st = self.channel.state()
        except ChannelError:
            st = None
        self.state = st
        now = self.clock()
        if st is not None:
            self.phase = "ok"
            self._attach(st)
            self._first = False
            return
        code = self.proc.exit_code() if self.proc is not None else None
        if self.proc is not None and code is not None:
            pid = self.proc.pid
            self._set_proc(None)
            if self.marker.active():
                self.phase = "stopped"
                self._event("exited", f"HUB (PID {pid}) zakończył się (kod {code}) po celowym zatrzymaniu: bez restartu")
            elif code == 0:
                self.phase = "not_started"
                self._event("exited", f"HUB (PID {pid}) zakończył się normalnie (kod 0): bez restartu")
            elif not self.supervising:
                self.phase = "unreachable"
                self._event("exited", f"HUB (PID {pid}) zakończył się z kodem {code}; restart należy do managera-nadzorcy")
            elif self.policy.allow_restart(now):
                self._event("restarted", f"HUB (PID {pid}) zakończył się z kodem {code}: restart {self.policy.count} z {MAX_RESTARTS}")
                self._start()
            else:
                self.phase = "gave_up"
                self._event("gave_up", f"HUB (PID {pid}) zakończył się z kodem {code}: limit {MAX_RESTARTS} restartów wyczerpany")
            self._first = False
            return
        fresh = self.proc is None and self._first and self.supervising and self.phase == "not_started"
        if fresh and self.marker.active():
            # Wariant A (decyzja właściciela 2026-10-19): zapis chroni przed wskrzeszeniem HUB-a tylko, dopóki działa jakiś manager
            # albo HUB. Świeży start managera, gdy nie działa ani inny manager (mamy blokadę nadzoru), ani HUB: kasuje zapis i uruchamia HUB.
            self.marker.clear()
            self._event("started", "HUB zatrzymany celowo wcześniej, ale nie działa ani HUB, ani inny manager: kasuję zapis i uruchamiam hub.exe --module none")
            self._start()
        elif self.proc is None and self.marker.active():
            self.phase = "stopped"
        elif fresh:
            self._event("started", "HUB nie odpowiada: uruchamiam hub.exe --module none")
            self._start()
        elif self.phase not in ("gave_up", "stopped"):
            since = self.seconds_since_start()
            self.phase = "starting" if since is not None and since < 30 else ("unreachable" if self.proc is not None or self.started_at else "not_started")
        self._first = False

    def close(self):
        """Zamknięcie okna: zwalnia blokadę nadzoru i uchwyt; HUB działa dalej."""
        with self._mu:
            self._closed = True
            self._set_proc(None)
            self.lock.release()
