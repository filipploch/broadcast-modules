"""E2d3c2: części managera bez okna: katalog module.json i konfiguracja, klient kanału (własny limit 2 s), wersja HUB-a,
model widoku (przyciski i paski), Debian (ping, warianty potwierdzenia), śledzenie logów.

Uruchomienie:  modules\\.venv\\Scripts\\python.exe -m unittest discover tests\\manager"""
import http.server
import json
import pathlib
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from manager import catalog, config as mconfig, debian, logs, version, view  # noqa: E402
from manager.channel import Channel, ChannelError  # noqa: E402


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- katalog i konfiguracja ---

class CatalogTest(unittest.TestCase):
    def test_pliki_z_repozytorium_jak_w_hub_ie(self):
        cat = catalog.scan(ROOT / "modules")
        self.assertEqual(cat.warnings, [])
        self.assertEqual([(m.id, m.button, m.log_name) for m in cat.modules],
                         [("nalf", "FUTSAL NALF", "futsal_nalf"), ("garbarnia", "GARBARNIA", "garbarnia")])

    def test_te_same_odrzucenia_co_w_hub_ie(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            write(d / "ok" / "module.json", '{"format":1,"id":"ok","button":"OK","script":"ok.py","port":1}')
            write(d / "zly" / "module.json", '{ to nie json')
            write(d / "niepelny" / "module.json", '{"format":1,"id":"np","script":"np.py"}')
            write(d / "literowka" / "module.json", '{"format":1,"id":"lit","button":"L","script":"l.py","port":1,"prot":2}')
            write(d / "format" / "module.json", '{"format":2,"id":"f2","button":"F","script":"f.py","port":1}')
            write(d / "dup1" / "module.json", '{"format":1,"id":"dup","button":"D1","script":"d1.py","port":1}')
            write(d / "dup2" / "module.json", '{"format":1,"id":"dup","button":"D2","script":"d2.py","port":1}')
            (d / "bez-pliku").mkdir()
            cat = catalog.scan(d)
            self.assertEqual([m.id for m in cat.modules], ["ok"])
            text = "\n".join(cat.warnings)
            for want in ("zly", "brak pól button, port", "literowka", "nieznany format 2", "dup1", "dup2"):
                self.assertIn(want, text)

    def test_brak_folderu_to_pusty_katalog(self):
        self.assertEqual(catalog.scan(pathlib.Path(tempfile.gettempdir()) / "nie-ma-takiego-folderu-xyz").modules, [])


class ConfigTest(unittest.TestCase):
    def test_kolejnosc_plikow_i_folder_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            c = mconfig.load(root=root)
            self.assertEqual((c.control_port, c.hub_port, c.source), (8079, 8080, "wartości wbudowane"))
            self.assertEqual(c.run_dir, root / "run")
            write(root / "hub" / "config" / "hub.example.json", '{"control_port": 8079, "hub_port": 8080}')
            self.assertIn("hub.example.json", mconfig.load(root=root).source)
            write(root / "hub" / "config" / "hub.json", json.dumps({"control_port": 18102, "state_file": str(root / "x" / "uslugi.json")}))
            c = mconfig.load(root=root)
            self.assertEqual((c.control_port, c.source, c.run_dir), (18102, "hub.json", root / "x"))
            other = root / "inny.json"
            write(other, '{"control_port": 18200}')
            c = mconfig.load(str(other), root=root)
            self.assertTrue(c.explicit)
            self.assertEqual(c.control_port, 18200)


# --- klient kanału ---

class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self._send(200, {"protocol": 1, "path": self.path})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        ok = self.headers.get("Content-Type") == "application/json" and self.headers.get("Origin") is None
        self._send(409 if ok else 415, {"ok": False, "reason": "session_open", "error": "Najpierw zamknij sesję transmisji"})

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ChannelTest(unittest.TestCase):
    def test_odpowiedzi_i_odmowy(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            ch = Channel(srv.server_address[1])
            self.assertEqual(ch.state()["protocol"], 1)
            code, res = ch.post("/module/stop")
            self.assertEqual(code, 409, "POST z application/json i bez Origin (inaczej atrapa daje 415)")
            self.assertIn("Najpierw zamknij", res["error"])
        finally:
            srv.shutdown()

    def test_brak_polaczenia(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        t0 = time.monotonic()
        with self.assertRaises(ChannelError) as cm:
            Channel(port).state()
        # Windows ponawia połączenie odrzucone na 127.0.0.1 przez ok. 2 s (pomiar z E2d1), więc limit managera (2 s) bywa pierwszy:
        # oba rodzaje błędu znaczą dla managera "HUB nie odpowiada"; ważne, że okno nie czeka dłużej niż limit
        self.assertIn(cm.exception.kind, ("unreachable", "timeout"))
        self.assertLess(time.monotonic() - t0, 2.6)

    def test_wlasny_limit_czasu_przy_atrapie_ktora_nie_odpowiada(self):
        ln = socket.socket()
        ln.bind(("127.0.0.1", 0))
        ln.listen(5)                                  # przyjmuje połączenie, nigdy nie odpowiada
        try:
            ch = Channel(ln.getsockname()[1], timeout=0.5)
            t0 = time.monotonic()
            with self.assertRaises(ChannelError) as cm:
                ch.state()
            self.assertEqual(cm.exception.kind, "timeout")
            self.assertLess(time.monotonic() - t0, 2.0)
            self.assertEqual(Channel(1).timeout, 2.0, "domyślny limit 2 s")
        finally:
            ln.close()


# --- wersja HUB-a ---

def st(protocol=1, commit="abc123"):
    return {"protocol": protocol, "hub": {"commit": commit}}


class VersionTest(unittest.TestCase):
    def git(self, last_rc=0, last="L", anc_rc=0):
        def run(root, *args):
            return (last_rc, last) if args[0] == "log" else (anc_rc, "")
        return run

    def test_protokol_rozstrzyga(self):
        n = version.check(st(protocol=2), ROOT, self.git())
        self.assertEqual([x.level for x in n], ["error"])
        self.assertIn("przebuduj", n[0].text)
        self.assertEqual(version.check(st(), ROOT, self.git()), [])

    def test_commit_tylko_ostrzega(self):
        cases = {"": "nieznana", "abc-dirty": "niezapisanymi"}
        for commit, word in cases.items():
            n = version.check(st(commit=commit), ROOT, self.git())
            self.assertTrue(n and all(x.level == "warn" for x in n) and any(word in x.text for x in n), (commit, n))
        n = version.check(st(), ROOT, self.git(anc_rc=1))
        self.assertTrue(any("starszy" in x.text for x in n))
        n = version.check(st(), ROOT, self.git(last_rc=None, last=""))
        self.assertTrue(any("Nie można sprawdzić" in x.text and x.level == "warn" for x in n))

    def test_prawdziwy_git_dla_commitu_z_repozytorium(self):
        import subprocess
        head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        self.assertEqual([x for x in version.check(st(commit=head), ROOT) if x.level == "error"], [])
        self.assertFalse(any("starszy" in x.text for x in version.check(st(commit=head), ROOT)))


# --- model widoku ---

CAT = catalog.Catalog(modules=[catalog.Module("nalf", "FUTSAL NALF", 8081, "futsal_nalf", 10, "futsal_nalf"),
                               catalog.Module("garbarnia", "GARBARNIA", 8081, "garbarnia", 20, "garbarnia")])


def state(active=None, session=None, protocol=1, stopping=False):
    return {"protocol": protocol, "hub": {"commit": "x", "stopping": stopping}, "active": active,
            "session": session or {"known": True, "open": False, "state": "none"}}


class ViewTest(unittest.TestCase):
    def texts(self, v):
        return [(b.text, b.color, b.enabled) for b in v.buttons]

    def test_hub_startuje_a_potem_nie_odpowiada(self):
        self.assertEqual(view.hub_phase(False, 5), "starting")
        self.assertEqual(view.hub_phase(False, 31), "unreachable")
        self.assertEqual(view.hub_phase(False, None, "stopped"), "stopped")
        v = view.build(CAT, None, "starting")
        self.assertEqual(v.banners[0].level, "info")
        self.assertIn("startuje", v.banners[0].text)
        self.assertTrue(all(not b.enabled and b.color == "grey" for b in v.buttons))
        v = view.build(CAT, None, "unreachable")
        self.assertEqual(v.banners[0].level, "error")

    def test_brak_aktywnego_modulu(self):
        v = view.build(CAT, state(), "ok")
        self.assertEqual(self.texts(v), [("URUCHOM FUTSAL NALF", "green", True), ("URUCHOM GARBARNIA", "green", True)])
        self.assertTrue(v.stop_hub_enabled)

    def test_aktywny_modul_czerwony_reszta_szara(self):
        v = view.build(CAT, state(active={"id": "nalf", "state": "running"}), "ok")
        self.assertEqual(self.texts(v), [("ZATRZYMAJ FUTSAL NALF", "red", True), ("URUCHOM GARBARNIA", "grey", False)])

    def test_startuje_zatrzymuje_sie_reczny_brak_folderu(self):
        v = view.build(CAT, state(active={"id": "nalf", "state": "starting"}), "ok")
        self.assertEqual(self.texts(v)[0], ("URUCHAMIANIE FUTSAL NALF…", "grey", False))
        v = view.build(CAT, state(active={"id": "nalf", "state": "stopping"}), "ok")
        self.assertEqual(self.texts(v)[0], ("ZATRZYMYWANIE FUTSAL NALF…", "grey", False))
        v = view.build(CAT, state(active={"id": "garbarnia", "state": "manual"}), "ok")
        self.assertEqual(self.texts(v)[1], ("ZATRZYMAJ GARBARNIA (ręcznie)", "red", True))
        only = catalog.Catalog(modules=[CAT.modules[1]])
        v = view.build(only, state(active={"id": "nalf", "button": "FUTSAL NALF", "state": "running", "missing": True}), "ok")
        self.assertIn(("ZATRZYMAJ FUTSAL NALF (brak folderu)", "red", True), self.texts(v))
        self.assertIn(("URUCHOM GARBARNIA", "grey", False), self.texts(v))

    def test_nieznany_modul_reczny_blokuje_starty(self):
        v = view.build(CAT, state(active={"id": "", "name": "hokej", "state": "manual_unknown"}), "ok")
        self.assertTrue(all(not b.enabled for b in v.buttons if b.action != "stop"))
        self.assertTrue(any("hokej" in b.text for b in v.banners))

    def test_niezgodny_protokol_blokuje_moduly_ale_nie_zatrzymanie_hub_a(self):
        v = view.build(CAT, state(protocol=2), "ok")
        self.assertTrue(all(not b.enabled for b in v.buttons))
        self.assertTrue(v.stop_hub_enabled)
        self.assertTrue(any(b.level == "error" and "protokół 2" in b.text for b in v.banners))

    def test_paski_sesji_i_drugi_manager(self):
        v = view.build(CAT, state(session={"known": True, "open": True, "state": "on_air"}), "ok")
        self.assertTrue(any("otwarta" in b.text for b in v.banners))
        v = view.build(CAT, state(session={"known": False}), "ok")
        self.assertTrue(any("nieznany" in b.text for b in v.banners))
        v = view.build(CAT, None, "stopped", supervising=False)
        self.assertFalse(v.start_hub_enabled)
        self.assertTrue(any("inny otwarty manager" in b.text for b in v.banners))
        self.assertTrue(view.build(CAT, None, "stopped").start_hub_enabled)


# --- Debian ---

PING_UP_PL = "Odpowiedź z 192.168.1.101: bajtów=32 czas<1 ms TTL=64\r\n"
PING_UP_EN = "Reply from 192.168.1.101: bytes=32 time<1ms TTL=64\r\n"
PING_NOTFOUND_PL = "Żądanie polecenia ping nie może znaleźć hosta debian.local. Sprawdź nazwę i ponów próbę.\r\n"
PING_NOTFOUND_EN = "Ping request could not find host debian.local. Please check the name and try again.\r\n"
PING_HOSTUNREACH_PL = "Odpowiedź z 192.168.1.100: Host docelowy jest nieosiągalny.\r\n"
PING_HOSTUNREACH_EN = "Reply from 192.168.1.100: Destination host unreachable.\r\n"
PING_TIMEOUT_PL = "Upłynął limit czasu żądania.\r\n"
PING_TIMEOUT_EN = "Request timed out.\r\n"


class DebianTest(unittest.TestCase):
    def test_stany_pingu_na_atrapach(self):
        cases = [(0, PING_UP_PL, "up"), (0, PING_UP_EN, "up"), (1, PING_NOTFOUND_PL, "down"), (1, PING_NOTFOUND_EN, "down"),
                 (1, PING_HOSTUNREACH_PL, "down"), (0, PING_HOSTUNREACH_EN, "down"),  # "host unreachable" bywa z kodem 0
                 (1, PING_TIMEOUT_PL, "unreachable"), (1, PING_TIMEOUT_EN, "unreachable"), (1, "", "unreachable")]
        for rc, out, want in cases:
            self.assertEqual(debian.ping("debian.local", runner=lambda h, rc=rc, out=out: (rc, out)), want, out)

    def test_brak_adresu_to_nie_wylaczony(self):
        self.assertEqual(debian.ping(""), "no_host")
        self.assertIn("brak adresu", debian.LABELS["no_host"])
        self.assertNotIn("wyłączony", debian.LABELS["no_host"])

    def test_prawdziwy_ping_do_siebie(self):
        self.assertEqual(debian.ping("127.0.0.1"), "up")

    def test_warianty_potwierdzenia(self):
        v = debian.confirm_variant("not_recording", session_open=False, session_known=True)
        self.assertEqual((v.confirmations, v.warnings), (1, []))
        v = debian.confirm_variant("recording", False, True)
        self.assertEqual(v.confirmations, 2)
        self.assertIn("przerwie nagranie", v.warnings[0])
        for rec in ("unknown", "disconnected", "hub_unreachable"):
            v = debian.confirm_variant(rec, False, True)
            self.assertEqual(v.confirmations, 2)
            self.assertIn("Nie można sprawdzić, czy trwa nagrywanie", v.warnings[0])

    def test_nie_nagrywa_i_sesja_otwarta_daje_ostrzezenie_o_sesji(self):
        v = debian.confirm_variant("not_recording", session_open=True, session_known=True)
        self.assertEqual(v.confirmations, 2)
        self.assertEqual(v.warnings, ["Sesja transmisji jest otwarta"])
        v = debian.confirm_variant("not_recording", session_open=None, session_known=False)
        self.assertEqual(v.confirmations, 2)
        self.assertIn("sesja", v.warnings[0])
        v = debian.confirm_variant("recording", True, True)
        self.assertEqual(len(v.warnings), 2, "oba ostrzeżenia naraz")

    def test_wylaczenie_bez_adresu(self):
        ok, msg = debian.shutdown("", "")
        self.assertFalse(ok)
        self.assertIn("DEBIAN_SSH_HOST", msg)


# --- logi ---

class LogsTest(unittest.TestCase):
    def test_nowe_wiersze_i_zmiana_pliku(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = pathlib.Path(d) / "a.log", pathlib.Path(d) / "b.log"
            a.write_bytes("pierwszy\r\ndrugi".encode())
            f = logs.Follower()
            self.assertEqual(f.follow(a), ["pierwszy"])
            with open(a, "ab") as h:
                h.write(" koniec\ntrzeci\n".encode())
            self.assertEqual(f.follow(a), ["drugi koniec", "trzeci"])
            b.write_text("nowy\n", encoding="utf-8")
            self.assertEqual(f.follow(b), ["nowy"])

    def test_log_modulu_biezacego_uruchomienia(self):
        s = {"hub": {"log_dir": "C:\\logi\\logs-1"}, "active": {"id": "nalf", "name": "futsal_nalf"}, "modules": []}
        self.assertEqual(logs.module_log(s), pathlib.Path("C:\\logi\\logs-1") / "modul-futsal_nalf.log")
        s = {"hub": {"log_dir": "C:\\l"}, "active": None, "last_module": {"id": "garbarnia"}, "modules": [{"id": "garbarnia", "log_name": "garbarnia"}]}
        self.assertEqual(logs.module_log(s), pathlib.Path("C:\\l") / "modul-garbarnia.log")
        self.assertIsNone(logs.module_log(None))


if __name__ == "__main__":
    unittest.main()


class HubButtonTest(unittest.TestCase):
    """Jeden przycisk HUB-a zmieniający stan (prośba właściciela 2026-10-19), jak przyciski modułów."""

    def b(self, v):
        return (v.hub_button.text, v.hub_button.color, v.hub_button.enabled, v.hub_button.action)

    def test_stany_przycisku(self):
        self.assertEqual(self.b(view.build(CAT, state(), "ok")), ("ZATRZYMAJ HUB", "red", True, "stop_hub"))
        self.assertEqual(self.b(view.build(CAT, state(stopping=True), "ok")), ("ZATRZYMYWANIE HUB…", "grey", False, ""))
        self.assertEqual(self.b(view.build(CAT, None, "starting")), ("URUCHAMIANIE HUB…", "grey", False, ""))
        for phase in ("stopped", "gave_up", "not_started", "unreachable"):
            self.assertEqual(self.b(view.build(CAT, None, phase)), ("URUCHOM HUB", "green", True, "start_hub"), phase)
        self.assertEqual(self.b(view.build(CAT, None, "stopped", supervising=False)), ("URUCHOM HUB", "grey", False, ""),
                         "drugi manager nie uruchamia HUB-a")


class OdmowaStartuTest(unittest.TestCase):
    """Zgłoszone w próbie E2d3c2: Garbarnia nie startowała (stara baza), a w managerze nie było widać dlaczego."""

    def test_pasek_z_powodem_gdy_modul_nie_wystartowal(self):
        s = state()
        s["last_module"] = {"id": "garbarnia", "status": "error",
                            "error": "odmowa startu (kod 3): BŁĄD: moduł garbarnia NIE został uruchomiony — baza jest na starszej wersji migracji"}
        v = view.build(CAT, s, "ok")
        err = [b.text for b in v.banners if b.level == "error"]
        self.assertTrue(any("GARBARNIA nie działa" in t and "starszej wersji migracji" in t for t in err), err)
        self.assertEqual([b.enabled for b in v.buttons], [True, True], "można uruchomić moduł ponownie (np. po migracji)")
        s["last_module"]["status"] = "stopped"
        self.assertFalse(any(b.level == "error" for b in view.build(CAT, s, "ok").banners))

    def test_surowe_wyjscie_modulu_w_zakladce(self):
        s = {"hub": {"log_dir": "C:\l"}, "active": None, "last_module": {"id": "garbarnia"}, "modules": [{"id": "garbarnia", "log_name": "garbarnia"}]}
        self.assertEqual(logs.module_output_log(s), pathlib.Path("C:\l") / "modul-garbarnia.wyjscie.log")
