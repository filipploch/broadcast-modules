"""E2d3c2: nadzór HUB-a przez manager (manager/hub_process.py): restart tylko po awarii, limit i zerowanie, celowe zatrzymanie zapisane
w pliku, jeden nadzorca, przejmowanie procesu po numerze tylko przy zgodnym czasie utworzenia.

Uruchomienie:  modules\\.venv\\Scripts\\python.exe -m unittest discover tests\\manager"""
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from manager import config as mconfig  # noqa: E402
from manager.channel import ChannelError  # noqa: E402
from manager.hub_process import (MAX_RESTARTS, ProcHandle, RestartPolicy, StopMarker, Supervisor,  # noqa: E402
                                 SupervisorLock)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeProc:
    def __init__(self, pid, created_unix=0.0, created_ft=1):
        self.pid, self._created_unix, self._created_ft = pid, created_unix, created_ft
        self.code = None

    def exit_code(self):
        return self.code

    def created_ft(self):
        return self._created_ft

    def created_unix(self):
        return self._created_unix

    def close(self):
        pass


class FakeChannel:
    """up=True: /state odpowiada; post /hub/stop zwraca stop_code."""

    def __init__(self):
        self.up = False
        self.pid = 0
        self.uptime = 0
        self.stop_code = 202
        self.posts = []

    def state(self):
        if not self.up:
            raise ChannelError("unreachable", "brak")
        return {"protocol": 1, "hub": {"pid": self.pid, "uptime_s": self.uptime, "commit": "x"}, "session": {"known": True}}

    def post(self, path, body=None):
        self.posts.append(path)
        return self.stop_code, ({"ok": True} if self.stop_code == 202 else {"error": "Najpierw zamknij sesję transmisji"})


class Env:
    """Nadzorca z atrapami: kanału, procesu i uruchamiania (każde uruchomienie = nowy FakeProc)."""

    def __init__(self, run_dir, clock=None, channel=None):
        self.clock = clock or Clock()
        self.channel = channel or FakeChannel()
        self.procs = {}
        self.launches = 0
        cfg = mconfig.HubConfig(root=ROOT, config_path=None, explicit=False, source="test", hub_port=1, control_port=1,
                                modules_dir=ROOT / "modules", run_dir=pathlib.Path(run_dir))
        self.sup = Supervisor(cfg, ROOT / "hub" / "hub.exe", channel=self.channel, clock=self.clock, wall=lambda: 5000.0,
                              launcher=self._launch, open_proc=self._open)

    def _launch(self):
        self.launches += 1
        pid = 100 + self.launches
        self.procs[pid] = FakeProc(pid, created_unix=5000.0, created_ft=pid * 10)
        return pid

    def _open(self, pid):
        return self.procs.get(pid)

    def hub_up(self):
        """HUB uruchomiony przez nadzorcę odpowiada na kanale."""
        self.channel.up, self.channel.pid = True, 100 + self.launches
        self.sup.tick()

    def crash(self, code):
        self.procs[100 + self.launches].code = code
        self.channel.up = False
        self.sup.tick()


class PolicyTest(unittest.TestCase):
    def test_trzy_restarty_potem_odmowa_i_zerowanie_po_5_min(self):
        p = RestartPolicy()
        p.note_start(0)
        self.assertEqual([p.allow_restart(t) for t in (10, 20, 30, 40)], [True, True, True, False])
        p.note_start(100)
        self.assertTrue(p.allow_restart(100 + 300))   # 5 minut stabilnej pracy: licznik od zera
        self.assertEqual(p.count, 1)


class SupervisorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = pathlib.Path(self.tmp.name)
        self.envs = []

    def tearDown(self):
        for e in self.envs:
            e.sup.close()
        self.tmp.cleanup()

    def env(self, **kw):
        e = Env(self.run, **kw)
        self.envs.append(e)
        return e

    def test_start_managera_uruchamia_hub_gdy_nie_odpowiada(self):
        e = self.env()
        e.sup.tick()
        self.assertEqual(e.launches, 1)
        self.assertEqual(e.sup.phase, "starting")
        e.hub_up()
        self.assertEqual(e.sup.phase, "ok")

    def test_podlaczenie_do_dzialajacego_hub_a_bez_drugiego_startu(self):
        e = self.env()
        e.procs[555] = FakeProc(555, created_unix=5000.0 - 120)
        e.channel.up, e.channel.pid, e.channel.uptime = True, 555, 120
        e.sup.tick()
        self.assertEqual(e.launches, 0)
        self.assertIs(e.sup.proc, e.procs[555])

    def test_awaria_restart_najwyzej_3_razy_z_rzedu(self):
        e = self.env()
        e.sup.tick()
        e.hub_up()
        for i in range(MAX_RESTARTS):
            e.clock.t += 10
            e.crash(1)
            self.assertEqual(e.launches, 2 + i, f"restart {i + 1}")
            e.hub_up()
        e.clock.t += 10
        e.crash(1)
        self.assertEqual(e.launches, 1 + MAX_RESTARTS)
        self.assertEqual(e.sup.phase, "gave_up")

    def test_licznik_zerowany_po_5_minutach_stabilnej_pracy(self):
        e = self.env()
        e.sup.tick()
        e.hub_up()
        for _ in range(MAX_RESTARTS):
            e.clock.t += 10
            e.crash(1)
            e.hub_up()
        e.clock.t += 301
        e.crash(1)
        self.assertEqual(e.launches, 2 + MAX_RESTARTS, "po 5 min stabilnej pracy kolejna awaria daje restart")

    def test_kod_0_bez_restartu(self):
        e = self.env()
        e.sup.tick()
        e.hub_up()
        e.crash(0)
        self.assertEqual(e.launches, 1)
        self.assertEqual(e.sup.phase, "not_started")

    def test_po_celowym_zatrzymaniu_zaden_kod_nie_daje_restartu(self):
        for code in (0, 1, 3221225786):  # 3221225786 = 0xC000013A (zamknięcie konsoli)
            with self.subTest(code=code):
                StopMarker(self.run).clear()
                e = self.env()
                e.sup.tick()
                e.hub_up()
                ok, _ = e.sup.stop_hub()
                self.assertTrue(ok)
                self.assertTrue(StopMarker(self.run).active(), "znacznik zatrzymania w pliku")
                e.crash(code)
                self.assertEqual(e.launches, 1, f"kod {code} po celowym zatrzymaniu nie może dać restartu")
                self.assertEqual(e.sup.phase, "stopped")
                e.sup.close()
                self.envs.remove(e)

    def test_odmowa_hub_a_przy_stop_nie_zapisuje_znacznika(self):
        e = self.env()
        e.sup.tick()
        e.hub_up()
        e.channel.stop_code = 409
        ok, msg = e.sup.stop_hub()
        self.assertFalse(ok)
        self.assertIn("Najpierw zamknij", msg)
        self.assertFalse(StopMarker(self.run).active())

    def test_ponowne_otwarcie_managera_respektuje_celowe_zatrzymanie(self):
        e = self.env()
        e.sup.tick()
        e.hub_up()
        e.sup.stop_hub()
        e.crash(0)
        e.sup.close()
        self.envs.remove(e)
        e2 = self.env()                       # nowe okno managera
        e2.sup.tick()
        self.assertEqual(e2.launches, 0, "po celowym zatrzymaniu nowy manager nie uruchamia HUB-a sam")
        self.assertEqual(e2.sup.phase, "stopped")
        e2.sup.start(by_user=True)            # przycisk "Uruchom HUB"
        self.assertEqual(e2.launches, 1)
        self.assertFalse(StopMarker(self.run).active(), "przycisk Uruchom HUB kasuje znacznik")

    def test_dwa_managery_jeden_restart(self):
        a = self.env()
        b = self.env(clock=a.clock, channel=a.channel)
        b.procs = a.procs                     # ten sam HUB widziany przez oba
        a.sup.tick()
        b.sup.tick()
        self.assertTrue(a.sup.supervising)
        self.assertFalse(b.sup.supervising, "drugi manager nie dostaje blokady nadzoru")
        self.assertEqual(a.launches + b.launches, 1, "jeden start HUB-a")
        a.hub_up()
        b.sup.tick()
        self.assertIs(b.sup.proc, a.procs[101])
        a.procs[101].code = 1
        a.channel.up = False
        a.sup.tick()
        b.sup.tick()
        self.assertEqual(a.launches + b.launches, 2, "awaria: jeden restart, nie dwa")
        self.assertEqual(b.launches, 0)

    def test_nadzor_przechodzi_na_drugi_manager_po_zamknieciu_pierwszego(self):
        a = self.env()
        b = self.env(clock=a.clock, channel=a.channel)
        a.sup.tick()
        b.sup.tick()
        a.sup.close()
        self.envs.remove(a)
        b.sup.tick()
        self.assertTrue(b.sup.supervising)

    def test_niezgodny_czas_utworzenia_to_nie_ten_proces(self):
        e = self.env()
        e.procs[777] = FakeProc(777, created_unix=5000.0 - 3600)   # proces z tym numerem powstał godzinę temu
        e.channel.up, e.channel.pid, e.channel.uptime = True, 777, 60  # a HUB pracuje od minuty
        e.sup.tick()
        self.assertIsNone(e.sup.proc)
        self.assertTrue(any(ev.kind == "not_same_process" for ev in e.sup.events))
        e.procs[777].code = 1                                        # "ten" proces kończy się błędem
        e.channel.up = False
        e.sup.tick()
        self.assertEqual(e.launches, 0, "bez zgodnego procesu reguła kodu wyjścia nie jest stosowana")

    def test_zapis_managera_rozstrzyga_tozsamosc_procesu(self):
        e = self.env()
        e.sup.tick()                                                 # uruchomił HUB 101 i zapisał (pid, created_ft)
        e.sup._set_proc(None)
        e.procs[101] = FakeProc(101, created_unix=5000.0, created_ft=999)  # numer użyty ponownie przez inny proces
        e.channel.up, e.channel.pid, e.channel.uptime = True, 101, 0
        e.sup.tick()
        self.assertIsNone(e.sup.proc, "zapisany czas utworzenia inny: nie przejmujemy")


class RealProcessTest(unittest.TestCase):
    def test_uchwyt_procesu_czas_utworzenia_i_kod_wyjscia(self):
        pr = subprocess.Popen([sys.executable, "-c", "import time, sys; time.sleep(30)"])
        try:
            h = ProcHandle.open(pr.pid)
            self.assertIsNotNone(h)
            self.assertLess(abs(h.created_unix() - time.time()), 30)
            self.assertIsNone(h.exit_code())
            pr.kill()
            pr.wait()
            self.assertEqual(h.exit_code(), 1)
            h.close()
        finally:
            if pr.poll() is None:
                pr.kill()

    def test_blokada_nadzoru_w_drugim_procesie(self):
        with tempfile.TemporaryDirectory() as d:
            lock = SupervisorLock(pathlib.Path(d))
            self.assertTrue(lock.acquire())
            code = ("import sys, pathlib; sys.path.insert(0, %r); from manager.hub_process import SupervisorLock; "
                    "sys.exit(0 if SupervisorLock(pathlib.Path(%r)).acquire() else 7)") % (str(ROOT), d)
            self.assertEqual(subprocess.run([sys.executable, "-c", code]).returncode, 7, "drugi proces nie dostaje blokady")
            lock.release()
            self.assertEqual(subprocess.run([sys.executable, "-c", code]).returncode, 0, "po zwolnieniu blokada jest wolna")


if __name__ == "__main__":
    unittest.main()
