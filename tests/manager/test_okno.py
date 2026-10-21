"""E2d3c2: okno broadcast_manager.py w trybie testowym textual (bez prawdziwego HUB-a): przyciski z module.json, stan z /state,
odmowa HUB-a jako komunikat, potwierdzenie przy wyłączaniu Debiana; brak textual = czytelny komunikat bez tracebacku.
Wymaga textual (modules\\requirements-manager.txt); bez niego testy okna są pomijane."""
import asyncio
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

from manager.channel import ChannelError  # noqa: E402


class FakeChannel:
    def __init__(self):
        self.active = None
        self.posts = []
        self.session = {"known": True, "open": False, "state": "none"}

    def state(self):
        return {"protocol": 2, "hub": {"pid": 0, "uptime_s": 1, "commit": "", "stopping": False, "hub_log": "", "log_dir": ""},
                "modules": [], "active": self.active, "session": self.session, "recorder": {"connected": False}, "last_module": {}}

    def recorder(self):
        raise ChannelError("timeout", "brak")

    def post(self, path, body=None):
        self.posts.append((path, body))
        if path == "/module/start":
            self.active = {"id": body["id"], "state": "running", "name": "futsal_nalf"}
            return 202, {"ok": True}
        return 409, {"ok": False, "reason": "session_open", "error": "Najpierw zamknij sesję transmisji"}


@unittest.skipUnless(HAVE_TEXTUAL, "brak textual w tym środowisku (modules\\requirements-manager.txt)")
class OknoTest(unittest.TestCase):
    def run_app(self, scenario):
        import broadcast_manager as bm
        from manager.hub_process import Supervisor
        with tempfile.TemporaryDirectory() as d:
            app = bm.BroadcastManager()
            app.cfg.run_dir = pathlib.Path(d)
            fake = FakeChannel()
            launches = []
            app.sup = Supervisor(app.cfg, bm.HUB_EXE, channel=fake, launcher=lambda: launches.append(1) or 0, open_proc=lambda pid: None)

            async def go():
                async with app.run_test(size=(140, 45)) as pilot:
                    try:
                        await scenario(app, pilot, fake)
                    finally:
                        app.sup.close()
            asyncio.run(go())
            self.assertEqual(launches, [], "HUB odpowiada: manager niczego nie uruchamia")

    def test_przyciski_z_module_json_start_i_odmowa_zatrzymania(self):
        async def scenario(app, pilot, fake):
            await pilot.pause(1.5)
            labels = [str(b.label) for b in app.query("#module-buttons Button")]
            self.assertEqual(labels, ["URUCHOM FUTSAL NALF", "URUCHOM GARBARNIA"])
            hub_btn = app.query_one("#btn-hub")
            self.assertEqual((str(hub_btn.label), hub_btn.disabled), ("ZATRZYMAJ HUB", False), "jeden przycisk HUB-a, gdy HUB działa")
            self.assertEqual(len(app.query("#btn-hub-stop")) + len(app.query("#btn-hub-start")), 0, "bez dwóch osobnych przycisków")
            await pilot.click("#module-buttons Button")
            await pilot.pause(2.5)
            self.assertIn(("/module/start", {"id": "nalf"}), fake.posts)
            labels = [str(b.label) for b in app.query("#module-buttons Button")]
            self.assertEqual(labels, ["ZATRZYMAJ FUTSAL NALF", "URUCHOM GARBARNIA"])
            self.assertTrue(app.query("#module-buttons Button")[1].disabled, "drugi moduł szary i nieaktywny")
            await pilot.click("#module-buttons Button")
            await pilot.pause(1.5)
            log = "\n".join(str(l) for l in app.query_one("#log-system").lines)
            self.assertIn("Najpierw zamknij sesję transmisji", log)
        self.run_app(scenario)

    def test_wylaczenie_debiana_bez_informacji_o_nagrywaniu_daje_dwa_potwierdzenia(self):
        async def scenario(app, pilot, fake):
            await pilot.pause(1.5)
            app.run_worker(app._debian_prepare, thread=True)
            await pilot.pause(1.0)
            screen = app.screen
            texts = " ".join(str(l.render()) for l in screen.query("Label"))
            self.assertIn("Nie można sprawdzić, czy trwa nagrywanie", texts)
            await pilot.click("#yes")
            await pilot.pause(0.5)
            self.assertIn("Na pewno", " ".join(str(l.render()) for l in app.screen.query("Label")), "drugie, osobne potwierdzenie")
            await pilot.click("#no")
            await pilot.pause(0.3)
        self.run_app(scenario)


@unittest.skipUnless(HAVE_TEXTUAL, "brak textual w tym środowisku (modules\\requirements-manager.txt)")
class WidocznoscPrzyciskowTest(unittest.TestCase):
    """Zgłoszone w próbie ręcznej 2026-10-19: przy typowej wysokości okna brakowało przycisku GARBARNIA (kontener przycisków
    dostawał resztę miejsca, czyli 1 wiersz, i ucinał drugi przycisk)."""

    def test_oba_przyciski_widoczne_przy_niskim_oknie(self):
        import broadcast_manager as bm
        from manager.hub_process import Supervisor
        for size in ((120, 30), (100, 24)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as d:
                app = bm.BroadcastManager()
                app.cfg.run_dir = pathlib.Path(d)
                app.sup = Supervisor(app.cfg, bm.HUB_EXE, channel=FakeChannel(), launcher=lambda: 0, open_proc=lambda pid: None)

                async def go():
                    async with app.run_test(size=size) as pilot:
                        try:
                            await pilot.pause(1.5)
                            box = app.query_one("#module-buttons").region
                            buttons = list(app.query("#module-buttons Button"))
                            self.assertEqual([str(b.label) for b in buttons], ["URUCHOM FUTSAL NALF", "URUCHOM GARBARNIA"])
                            for b in buttons:
                                r = b.region
                                self.assertTrue(r.height > 0 and box.y <= r.y and r.y + r.height <= box.y + box.height,
                                                f"{b.label}: {r} poza kontenerem {box} (okno {size})")
                        finally:
                            app.sup.close()
                asyncio.run(go())


class BrakTextualTest(unittest.TestCase):
    def test_bez_textual_komunikat_z_poleceniem_instalacji_bez_tracebacku(self):
        # Python bez dostępu do pakietów venv (-S: bez site-packages, -I: izolacja), więc textual na pewno brak
        r = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "broadcast_manager.py")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=ROOT, timeout=30)
        self.assertEqual(r.returncode, 1)
        self.assertIn("pip install -r modules\\requirements-manager.txt", r.stderr)
        self.assertNotIn("Traceback", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
