"""E2d3a: okrojony broadcast_manager.py: nazwa modułu z konfiguracji HUB-a (tylko odczyt) i łagodne zatrzymanie HUB-a.

Uruchomienie:  python -m unittest discover tests/manager   (z katalogu głównego; nie wymaga textual)"""
import json
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from broadcast_manager_hub import hub_exe_stale, hub_module_choice, start_hub, stop_hub  # noqa: E402

import os  # noqa: E402


class StaryHubExe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.exe = self.dir / "hub.exe"
        self.exe.write_bytes(b"x")
        self.src = self.dir / "wol.go"
        self.src.write_text("package main", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _times(self, exe, src):
        os.utime(self.exe, (exe, exe))
        os.utime(self.src, (src, src))

    def test_zrodlo_nowsze_niz_exe_daje_ostrzezenie(self):
        self._times(1_000_000, 2_000_000)
        msg = hub_exe_stale(self.exe, self.dir)
        self.assertIsNotNone(msg)
        self.assertIn("wol.go", msg)
        self.assertIn("go build", msg)

    def test_exe_nowszy_bez_ostrzezenia(self):
        self._times(2_000_000, 1_000_000)
        self.assertIsNone(hub_exe_stale(self.exe, self.dir))

    def test_testy_go_nie_licza_sie(self):
        self._times(2_000_000, 1_000_000)
        t = self.dir / "wol_test.go"
        t.write_text("package main", encoding="utf-8")
        os.utime(t, (3_000_000, 3_000_000))
        self.assertIsNone(hub_exe_stale(self.exe, self.dir))

    def test_brak_exe_albo_zrodel_bez_ostrzezenia(self):
        self.assertIsNone(hub_exe_stale(self.dir / "brak.exe", self.dir))
        self.src.unlink()
        self.assertIsNone(hub_exe_stale(self.exe, self.dir))


class NazwaModulu(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, data):
        (self.dir / name).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")

    def test_hub_json_wygrywa_z_przykladem(self):
        self._write("hub.json", {"module": "garbarnia"})
        self._write("hub.example.json", {"module": "nalf"})
        self.assertEqual(hub_module_choice(self.dir), ("garbarnia", "hub.json"))

    def test_bez_hub_json_przyklad(self):
        self._write("hub.example.json", {"module": "nalf"})
        self.assertEqual(hub_module_choice(self.dir), ("nalf", "hub.example.json (brak hub.json)"))

    def test_bez_plikow_wartosc_wbudowana(self):
        name, source = hub_module_choice(self.dir)
        self.assertEqual(name, "nalf")
        self.assertIn("wbudowane", source)

    def test_pusty_modul_oznacza_brak(self):
        self._write("hub.json", {"module": ""})
        self.assertEqual(hub_module_choice(self.dir)[0], "")

    def test_uszkodzony_plik_jest_zgloszony(self):
        self._write("hub.json", "{ to nie json")
        name, source = hub_module_choice(self.dir)
        self.assertEqual(name, "?")
        self.assertIn("uszkodzony", source)

    def test_przyklad_z_repozytorium_zgodny_z_hubem(self):
        # hub/config.go: defaultHubConfig().Module == "nalf" (test HUB-a pilnuje zgodności z hub.example.json)
        data = json.loads((ROOT / "hub" / "config" / "hub.example.json").read_text(encoding="utf-8"))
        self.assertEqual(data["module"], "nalf")


@unittest.skipUnless(sys.platform == "win32", "CTRL_BREAK tylko na Windowsie")
class ZatrzymanieHuba(unittest.TestCase):
    """Atrapa HUB-a: proces Pythona uruchomiony tak jak HUB (własna grupa procesów, wyjście do potoku)."""

    def _atrapa(self, body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        script = pathlib.Path(tmp.name) / "atrapa.py"
        script.write_text(textwrap.dedent(body), encoding="utf-8")
        # te same flagi co w start_hub (własna grupa procesów), interpreter z argumentem zamiast hub.exe
        proc = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        self.assertEqual(proc.stdout.readline().strip(), "gotowy")
        return proc

    def test_lagodne_zamkniecie_bez_wymuszenia(self):
        proc = self._atrapa("""
            import signal, sys, time
            signal.signal(signal.SIGBREAK, lambda *a: sys.exit(0))
            print("gotowy", flush=True)
            while True:
                time.sleep(0.1)
        """)
        logs = []
        t0 = time.monotonic()
        rc = stop_hub(proc, logs.append, grace_s=10)
        self.assertEqual(rc, 0)
        self.assertLess(time.monotonic() - t0, 5)
        self.assertFalse(any("wymuszeniem" in l for l in logs), logs)

    def test_brak_reakcji_wymuszenie_po_limicie(self):
        proc = self._atrapa("""
            import signal, time
            signal.signal(signal.SIGBREAK, signal.SIG_IGN)
            print("gotowy", flush=True)
            while True:
                time.sleep(0.1)
        """)
        logs = []
        stop_hub(proc, logs.append, grace_s=1)
        self.assertIsNotNone(proc.poll())
        self.assertTrue(any("wymuszeniem" in l for l in logs), logs)

    def test_proces_juz_zakonczony(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        self.assertIsNone(stop_hub(proc, lambda m: None))

    def test_start_hub_daje_wlasna_grupe_procesow(self):
        # start_hub z podmienionym poleceniem: proces startuje z potokiem we własnej grupie i daje się łagodnie zatrzymać
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        script = pathlib.Path(tmp.name) / "atrapa.py"
        script.write_text(textwrap.dedent("""
            import signal, sys, time
            signal.signal(signal.SIGBREAK, lambda *a: sys.exit(0))
            print("gotowy", flush=True)
            while True:
                time.sleep(0.1)
        """), encoding="utf-8")
        exe = pathlib.Path(tmp.name) / "hub.exe"  # nazwa tylko dla start_hub; Popen dostaje interpreter
        orig = subprocess.Popen

        def popen(args, **kw):
            return orig([sys.executable, str(script)], **kw)
        subprocess.Popen = popen
        try:
            proc = start_hub(exe, pathlib.Path(tmp.name))
        finally:
            subprocess.Popen = orig
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        self.assertEqual(proc.stdout.readline().strip(), "gotowy")
        self.assertEqual(stop_hub(proc, lambda m: None, grace_s=10), 0)


if __name__ == "__main__":
    unittest.main()
