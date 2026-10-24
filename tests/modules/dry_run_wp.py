"""Proba z prawdziwym HUB-em i prawdziwym PHP: instancje WordPressa modulow (WP-1, krok W3, scenariusze W1-W6).

    modules\\.venv\\Scripts\\python.exe tests\\modules\\dry_run_wp.py [futsal_nalf]

Buduje swiezo do wp-local/dryrun-wp/: hub.exe (z wpisanym commitem "dryrun") i timer-plugin.exe. Porty testowe: HUB 18110, modul "proba"
18111 (drugi modul "druga" 18113), kanal sterujacy 18112. Instancje WP uzywaja PRAWDZIWYCH portow z blokow "wp": 8091 ("proba") i 8092
("druga"), prawdziwego PHP i baz p8091/p8092 z wp-local (to bazy prob; WP moze w nich zapisac swoje opcje). Pliki .bat sprawdza ten sam
plik hub\\hub.exe z repozytorium (polecenie "hub.exe wp <modul>", katalog modulow repozytorium: nalf 8091, garbarnia 8092).
  W1. Start modulu kanalem sterujacym: HUB uruchamia WP modulu (port 8091 odpowiada), /status podaje instancje; modul startuje.
  W2. Zatrzymanie modulu zatrzymuje WP (port 8091 wolny).
  W3. Dziala instancja DRUGIEGO modulu (uruchomiona jak z .bat): start modulu zamyka ja bez restartu HUB-a i uruchamia wlasciwa.
  W4. Dziala juz WLASCIWA instancja (z .bat): zostaje ta sama (ten sam PID, bez restartu), HUB ja przejmuje; zatrzymanie modulu zamyka ja.
  W5. Port WP zajety przez obcy proces: modul i tak startuje, w /status ostrzezenie, obcy proces nietkniety.
  W6. Zabicie procesu WP w trakcie pracy modulu: HUB uruchamia go ponownie.
  W8. (WP-2) Modul pod HUB-em laczy sie z WP (/api/wp/state: polaczony, logowanie, lista), zglasza brak WP (W5) i powrot po restarcie WP (W6).
  W7. Sprzatanie: po probie nie zostaje proces z proby (porty 8091/8092 i 181xx wolne).
Wymaga wolnych portow 8091, 8092, 18110-18113.
"""
import json, os, pathlib, shutil, signal, socket, subprocess, sys, time, urllib.error, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
MODULE = ARGS[0] if ARGS else "futsal_nalf"
DRY = REPO / "wp-local" / "dryrun-wp"
LOGS = DRY / "logs"
OUT = REPO / "wp-local" / "tests-out" / "dry_run_wp.txt"
CLI_HUB = REPO / "hub" / "hub.exe"
HUB_PORT, MOD_PORT, CTL_PORT, MOD2_PORT = 18110, 18111, 18112, 18113
WP1, WP2 = 8091, 8092
PORTS = (HUB_PORT, MOD_PORT, CTL_PORT, MOD2_PORT, WP1, WP2)
HUB = f"http://127.0.0.1:{HUB_PORT}"
CTL = f"http://127.0.0.1:{CTL_PORT}"
lines, results, spawned = [], {}, []
DB = None


def say(msg=""):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode(), flush=True)
    lines.append(msg)


def check(name, ok, detail=""):
    results[name] = bool(ok)
    say(f"{name}: {'ZALICZONY' if ok else 'NIEZALICZONY'} {detail}")
    return ok


def port_busy(p):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", p)) == 0


def wait_for(cond, timeout, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def status():
    return get_json(HUB + "/status")


def state():
    return get_json(CTL + "/state")


def ctl(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"} if method == "POST" else {}
    req = urllib.request.Request(CTL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except ValueError:
            return e.code, {}


def http_code(port, timeout=20):      # pierwsze zapytanie do świeżo uruchomionego WP (strona główna z danymi) bywa wolne; 5 s dawało sporadyczne HTTP 0
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def pid_alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def kill_tree(pid):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def listener_pid(port):
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ $_.OwningProcess }}"],
                         capture_output=True, text=True).stdout.split()
    return int(out[0]) if out and out[0].isdigit() else 0


def module_wp():
    """Stan WP widziany przez modul (WP-2): GET /api/wp/state modulu 'proba'."""
    return get_json(f"http://127.0.0.1:{MOD_PORT}/api/wp/state")


def wp_state():
    return status().get("wp", {})


def build():
    DRY.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    for name, cwd, target, extra in (("hub.exe", REPO / "hub", ".", ["-ldflags", "-X main.buildCommit=dryrun"]),
                                     ("timer-plugin.exe", REPO / "plugins" / "timer-plugin", "./cmd/timer-plugin", [])):
        r = subprocess.run(["go", "build", *extra, "-o", str(DRY / name), target], cwd=cwd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"Budowanie {name} nie powiodlo sie:\n{r.stderr}")
    (DRY / "hub" / "config").mkdir(parents=True, exist_ok=True)
    (DRY / "timer-plugin").mkdir(exist_ok=True)
    shutil.copy(REPO / "plugins" / "timer-plugin" / "config.json", DRY / "timer-plugin" / "config.json")
    plugins = {"timer-plugin": {
        "id": "timer-plugin", "name": "Timer Plugin", "type": "local", "args": [],
        "executable_path": str(DRY / "timer-plugin.exe"), "working_dir": str(DRY / "timer-plugin"), "env": ["PLUGIN_ID=timer-plugin"],
        "auto_start": True, "restart_on_crash": True, "max_restarts": 10, "restart_delay_ms": 3000, "startup_delay_ms": 1000,
        "health_check_interval": 10, "is_critical": False}}
    (DRY / "hub" / "config" / "plugins.json").write_text(json.dumps(plugins, indent=2), encoding="utf-8")
    (DRY / "hub" / "config" / "overlays.json").write_text("{}", encoding="utf-8")
    shutil.rmtree(DRY / "modules", ignore_errors=True)
    for folder, mid, port, wp in (("proba", "proba", MOD_PORT, WP1), ("druga", "druga", MOD2_PORT, WP2)):
        (DRY / "modules" / folder).mkdir(parents=True, exist_ok=True)
        (DRY / "modules" / folder / "module.json").write_text(json.dumps({
            "format": 1, "id": mid, "button": mid.upper(), "script": str(REPO / "tests" / "modules" / "dry_run_module.py"),
            "args": [MODULE], "port": port, "log_name": MODULE if mid == "proba" else "druga_log",
            "order": 1 if mid == "proba" else 2, "wp": {"port": wp, "title": mid}}, indent=2), encoding="utf-8")
    cfg = {
        "hub_port": HUB_PORT, "module": "proba", "modules_dir": str(DRY / "modules"), "control_port": CTL_PORT,
        "wp_dir": str(REPO / "wp-local"),
        "python_path": sys.executable, "module_dir": str(REPO / "modules" / MODULE), "module_ready_timeout_s": 90, "module_stop_grace_s": 10,
        "obs": {"enabled": False, "path": "", "ws_port": 0, "process_name": ""},
        "wol": {"enabled": False, "mac": "", "broadcast_addr": "255.255.255.255:9"},
        "state_file": str(DRY / "uslugi.json"),
    }
    (DRY / "hub.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def module_env():
    return {**os.environ, "BM_LOGS_DIR": str(LOGS), "DATABASE_URL": "sqlite:///" + DB.as_posix(),
            "BM_REQUIRED_PLUGINS": "timer-plugin", "PYTHONIOENCODING": "utf-8"}


def start_hub(tag):
    out = open(DRY / f"hub-konsola-{tag}.txt", "wb")
    pr = subprocess.Popen([str(DRY / "hub.exe"), "--config", str(DRY / "hub.json"), "--module", "none"], cwd=DRY / "hub", env=module_env(),
                          stdout=out, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    spawned.append(pr.pid)
    return pr


def start_module(mid):
    code, res = ctl("POST", "/module/start", {"id": mid})
    ok = code == 202 and wait_for(lambda: (state().get("active") or {}).get("state") == "running", 120)
    wait_for(lambda: state()["session"]["known"], 30)
    return ok, f"({code} {res})"


def stop_module():
    wait_for(lambda: state()["session"]["known"] and state()["session"].get("state") == "none", 30)
    code, res = ctl("POST", "/module/stop", {})
    ok = code == 202 and wait_for(lambda: state().get("active") is None, 60)
    return ok, f"({code} {res})"


def cli_wp(real_id):
    """Instancja jak z pliku .bat: hub\\hub.exe wp <modul> (okno w tle)."""
    pr = subprocess.Popen([str(CLI_HUB), "wp", real_id], stdout=open(DRY / f"wp-cli-{real_id}.txt", "wb"), stderr=subprocess.STDOUT,
                          creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    spawned.append(pr.pid)
    return pr


def main():
    global DB
    for p in PORTS:
        if port_busy(p):
            sys.exit(f"Port {p} jest zajety (poprzednia proba nie posprzatala albo dziala WP z .bat?). Niczego nie zabijam; sprawdz recznie.")
    if not CLI_HUB.exists():
        sys.exit("Brak hub\\hub.exe: zbuduj go przez hub\\build.bat.")
    r = subprocess.run([sys.executable, str(REPO / "tests" / "modules" / "prepare_dry_run.py"), MODULE], capture_output=True, text=True)
    if r.returncode:
        sys.exit("Przygotowanie bazy nie powiodlo sie:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    DB = REPO / "modules" / MODULE / "instance" / "database-proba.db"
    shutil.rmtree(LOGS, ignore_errors=True)
    shutil.rmtree(DRY / "timer-plugin" / "state", ignore_errors=True)
    (DRY / "uslugi.json").unlink(missing_ok=True)
    build()
    hub = blocker = cli = None
    try:
        hub = start_hub("1")
        if not check("W0 kanal sterujacy odpowiada", wait_for(lambda: state()["protocol"] >= 2, 30)):
            return
        st = state()
        check("W0b /status ma pole wp", "wp" in status(), f"({status().get('wp')})")
        check("W0c katalog modulow: bloki wp wczytane", all(m.get("port") for m in st["modules"]) and len(st["modules"]) == 2)

        say("\n== W1. Start modulu uruchamia WP")
        ok, d = start_module("proba")
        check("W1a modul uruchomiony kanalem", ok, d)
        check("W1b WP modulu odpowiada na porcie 8091", wait_for(lambda: http_code(WP1) in (200, 301, 302), 30), f"(HTTP {http_code(WP1)})")
        w = wp_state()
        check("W1c /status: instancja modulu proba, port 8091, dziala, wlasna (nie przejeta), bez ostrzezenia",
              w.get("module_id") == "proba" and w.get("port") == WP1 and w.get("running") and not w.get("adopted") and not w.get("warning"), f"({w})")
        wp_pid1 = listener_pid(WP1)
        spawned.append(wp_pid1)
        check("W1d port 8092 wolny (jedna instancja naraz)", not port_busy(WP2))
        okm = wait_for(lambda: module_wp().get("connected") is True, 60)
        mw = module_wp()
        check("W1e modul polaczony z WP (stan, adres, logowanie z pliku, lista z prawdziwego WP)",
              okm and mw.get("enabled") and mw.get("url") == f"http://127.0.0.1:{WP1}" and mw.get("has_auth") and isinstance(mw.get("items"), list),
              f"(connected={mw.get('connected')}, auth={mw.get('has_auth')}, pozycji={len(mw.get('items', []))}, bez kategorii={mw.get('unassigned')}, blad={mw.get('error')!r})")

        say("\n== W2. Zatrzymanie modulu zatrzymuje WP")
        ok, d = stop_module()
        check("W2a modul zatrzymany", ok, d)
        check("W2b WP zatrzymany, port 8091 wolny", wait_for(lambda: not port_busy(WP1), 20), f"(port {'zajety' if port_busy(WP1) else 'wolny'})")

        say("\n== W3. Instancja drugiego modulu zostaje zamknieta")
        cli = cli_wp("garbarnia")
        check("W3a instancja drugiego modulu (jak z .bat) dziala na 8092", wait_for(lambda: http_code(WP2) in (200, 301, 302), 40))
        pid_other = listener_pid(WP2)
        ok, d = start_module("proba")
        check("W3b modul proba wystartowal mimo to", ok, d)
        check("W3c instancja drugiego modulu zamknieta, wlasna dziala",
              wait_for(lambda: not port_busy(WP2) and http_code(WP1) in (200, 301, 302), 30), f"(8092 {'zajety' if port_busy(WP2) else 'wolny'}, 8091 HTTP {http_code(WP1)})")
        check("W3d HUB sie nie zrestartowal", hub.poll() is None)
        stop_module()
        wait_for(lambda: not port_busy(WP1), 20)

        say("\n== W4. Wlasciwa instancja z .bat zostaje (bez restartu) i jest zatrzymywana z modulem")
        cli = cli_wp("nalf")
        check("W4a instancja modulu (jak z .bat) dziala na 8091", wait_for(lambda: http_code(WP1) in (200, 301, 302), 40))
        pid_before = listener_pid(WP1)
        spawned.append(pid_before)
        ok, d = start_module("proba")
        check("W4b modul wystartowal", ok, d)
        time.sleep(2)
        w = wp_state()
        check("W4c ten sam proces (PID), bez restartu", listener_pid(WP1) == pid_before and pid_before, f"(przed {pid_before}, po {listener_pid(WP1)})")
        check("W4d /status: instancja przejeta", w.get("adopted") is True and w.get("pid") == pid_before, f"({w})")
        ok, d = stop_module()
        check("W4e zatrzymanie modulu zamyka rowniez przejeta instancje", ok and wait_for(lambda: not port_busy(WP1), 20), d)

        say("\n== W5. Port WP zajety przez obcy proces")
        blocker = subprocess.Popen([sys.executable, "-c",
                                    f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{WP1})); s.listen(); time.sleep(600)"])
        spawned.append(blocker.pid)
        wait_for(lambda: port_busy(WP1), 10)
        ok, d = start_module("proba")
        check("W5a modul wystartowal mimo zajetego portu WP", ok, d)
        w = wp_state()
        check("W5b /status: ostrzezenie o WP", bool(w.get("warning")), f"({w})")
        check("W5c obcy proces nietkniety", blocker.poll() is None)
        check("W5e modul zglasza brak polaczenia z WP (obcy proces nie odpowiada jak WP), nadal dziala",
              wait_for(lambda: module_wp().get("connected") is False, 40) and (state().get("active") or {}).get("state") == "running",
              f"({ {k: module_wp().get(k) for k in ('connected', 'error_kind')} })")
        stop_module()
        check("W5d po zatrzymaniu modulu obcy proces nadal zyje", blocker.poll() is None)
        blocker.kill()
        wait_for(lambda: not port_busy(WP1), 10)

        say("\n== W6. Zabicie WP w trakcie pracy modulu")
        ok, d = start_module("proba")
        check("W6a modul wystartowal", ok, d)
        check("W6b WP dziala", wait_for(lambda: http_code(WP1) in (200, 301, 302), 30))
        pid_a = listener_pid(WP1)
        spawned.append(pid_a)
        check("W6b2 modul widzi WP (connected)", wait_for(lambda: module_wp().get("connected") is True, 60))
        kill_tree(pid_a)
        check("W6c WP zabity", wait_for(lambda: not port_busy(WP1), 10))
        back = wait_for(lambda: http_code(WP1) in (200, 301, 302), 30)
        pid_b = listener_pid(WP1)
        spawned.append(pid_b)
        check("W6d HUB uruchomil WP ponownie (nowy proces)", back and pid_b and pid_b != pid_a, f"(PID {pid_a} -> {pid_b})")
        check("W6d2 modul wraca do polaczenia z WP", wait_for(lambda: module_wp().get("connected") is True, 60))
        stop_module()
        check("W6e po zatrzymaniu modulu port wolny", wait_for(lambda: not port_busy(WP1), 20))
    finally:
        say("\n== W7. Sprzatanie")
        if hub is not None and hub.poll() is None:
            os.kill(hub.pid, signal.CTRL_BREAK_EVENT)
            wait_for(lambda: hub.poll() is not None, 60)
            if hub.poll() is None:
                subprocess.run(["taskkill", "/F", "/PID", str(hub.pid)], capture_output=True)
        for pid in set(spawned):
            if pid and pid_alive(pid):
                kill_tree(pid)
        stray = []
        for port in PORTS:                              # porty proby: proces, ktory je trzyma, jest z proby (sprawdzone na starcie)
            pid = listener_pid(port)
            if pid:
                kill_tree(pid)
                stray.append(pid)
        time.sleep(1)
        left = [p for p in set(spawned) if p and pid_alive(p)] + stray
        ok = not any(port_busy(p) for p in PORTS)
        check("W7 nic nie zostalo", ok, f"(zajete porty: {[p for p in PORTS if port_busy(p)]}; zabite z portow: {stray})")
        failed = [k for k, v in results.items() if not v]
        say(f"\nWYNIK: {'WSZYSTKO ZALICZONE' if not failed else 'NIEZALICZONE: ' + ', '.join(failed)}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print(f"(wynik zapisany w {OUT})")


if __name__ == "__main__":
    main()
