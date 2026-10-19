"""Proba z prawdziwym HUB-em i KANALEM STERUJACYM managera (E2d3c1, scenariusze M1-M4 i M7). Bez managera (to E2d3c2):
skrypt rozmawia z HUB-em tak jak bedzie rozmawial manager (HTTP na 127.0.0.1:<control_port>).

    modules\\.venv\\Scripts\\python.exe tests\\modules\\dry_run_manager.py [futsal_nalf] [--krotka]

Buduje swiezo do wp-local/dryrun-manager/: hub.exe (z wpisanym commitem "dryrun"), timer-plugin.exe, atrape OBS i falszywy obs-ws-plugin.
Porty testowe: HUB 18100, modul 18101 (drugi modul 18103, nigdy nieuruchamiany), kanal sterujacy 18102, "obs-websocket" atrapy 18104.
Dwa moduly opisane plikami module.json w folderze proby: "proba" (dry_run_module.py) i "druga" (tylko do sprawdzenia wylacznosci).
  M1. HUB uruchomiony z --module none: dziala bez modulu; /state: protokol, commit, lista modulow, brak aktywnego; pierwsze wiersze hub.log.
  M2. Start modulu kanalem: modul dziala, laczy sie z HUB-em, HUB uruchamia timer-plugin; manager nie jest liczony jako plugin;
      (stala zasada prob) 3 minuty bez restartow.
  M3. Wylacznosc i ochrona kanalu: drugi modul i ten sam drugi raz odrzucone (409), nieznany (404), Origin (403), zly Content-Type (415).
  M4. Sesja otwarta: ZATRZYMAJ modul i ZATRZYMAJ HUB zablokowane ("Najpierw zamknij sesje transmisji"); po zamknieciu sesji
      zatrzymanie samego modulu: HUB, OBS i pluginy zostaja; potem ten sam modul uruchamia sie ponownie.
  M7. Modul uruchomiony recznie (poza HUB-em): rozpoznany po nazwie z rejestracji, start innego zablokowany, ZATRZYMAJ go zamyka.
  M8. Celowe zatrzymanie HUB-a kanalem (POST /hub/stop) przy zamknietej sesji: HUB konczy sie sam.
  M9. Sprzatanie: zadnego procesu z proby nie zostaje (po numerach procesow i po sciezce, nigdy po nazwie obrazu).
--krotka pomija 3 minuty z M2.
"""
import json, os, pathlib, shutil, signal, socket, subprocess, sys, time, urllib.error, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SHORT = "--krotka" in sys.argv
MODULE = ARGS[0] if ARGS else "futsal_nalf"
DRY = REPO / "wp-local" / "dryrun-manager"
LOGS = DRY / "logs"
OBS_BIN = DRY / "obs-bin"
OUT = REPO / "wp-local" / "tests-out" / "dry_run_manager.txt"
HUB_PORT, MOD_PORT, CTL_PORT, MOD2_PORT, OBS_PORT = 18100, 18101, 18102, 18103, 18104
PORTS = (HUB_PORT, MOD_PORT, CTL_PORT, MOD2_PORT, OBS_PORT)
HUB = f"http://127.0.0.1:{HUB_PORT}"
CTL = f"http://127.0.0.1:{CTL_PORT}"
MOD = f"http://127.0.0.1:{MOD_PORT}"
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


def ctl(method, path, body=None, headers=None):
    """Zadanie do kanalu sterujacego; zwraca (kod, odpowiedz JSON)."""
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"} if method == "POST" else {}
    h.update(headers or {})
    req = urllib.request.Request(CTL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except ValueError:
            return e.code, {}


def post(url):
    req = urllib.request.Request(url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def pid_alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def kill_tree(pid):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def procs_under_dry():
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith('%s', 'OrdinalIgnoreCase') } "
          "| ForEach-Object { $_.ProcessId }" % str(DRY).replace("'", "''"))
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def build():
    DRY.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    OBS_BIN.mkdir(exist_ok=True)
    targets = (("hub.exe", REPO / "hub", ".", DRY, ["-ldflags", "-X main.buildCommit=dryrun"]),
               ("timer-plugin.exe", REPO / "plugins" / "timer-plugin", "./cmd/timer-plugin", DRY, []),
               ("obs-atrapa.exe", REPO / "hub", "./cmd/obs-atrapa", OBS_BIN, []),
               ("fake-obs-plugin.exe", REPO / "hub", "./cmd/fake-obs-plugin", DRY, []))
    for name, cwd, target, outdir, extra in targets:
        r = subprocess.run(["go", "build", *extra, "-o", str(outdir / name), target], cwd=cwd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"Budowanie {name} nie powiodlo sie:\n{r.stderr}")
    (DRY / "hub" / "config").mkdir(parents=True, exist_ok=True)
    (DRY / "timer-plugin").mkdir(exist_ok=True)
    shutil.copy(REPO / "plugins" / "timer-plugin" / "config.json", DRY / "timer-plugin" / "config.json")
    common = {"restart_on_crash": True, "max_restarts": 10, "restart_delay_ms": 3000, "startup_delay_ms": 1000, "health_check_interval": 10,
              "is_critical": False, "auto_start": True, "type": "local", "args": []}
    plugins = {
        "timer-plugin": {**common, "id": "timer-plugin", "name": "Timer Plugin", "executable_path": str(DRY / "timer-plugin.exe"),
                         "working_dir": str(DRY / "timer-plugin"), "env": ["PLUGIN_ID=timer-plugin"]},
        "obs-ws-plugin": {**common, "id": "obs-ws-plugin", "name": "Fake OBS WS", "executable_path": str(DRY / "fake-obs-plugin.exe"),
                          "working_dir": str(DRY), "env": ["PLUGIN_ID=obs-ws-plugin", f"FAKE_OBS_STATE={DRY / 'fake-obs-state.json'}",
                                                            f"FAKE_OBS_LOG={DRY / 'fake-obs.log'}"]},
    }
    (DRY / "hub" / "config" / "plugins.json").write_text(json.dumps(plugins, indent=2), encoding="utf-8")
    (DRY / "hub" / "config" / "overlays.json").write_text("{}", encoding="utf-8")
    (DRY / "fake-obs-state.json").write_text(json.dumps({"stream": False, "record": False, "silent": False, "fail": False}), encoding="utf-8")
    shutil.rmtree(DRY / "modules", ignore_errors=True)
    for folder, mid, button, port in (("proba", "proba", "PROBA", MOD_PORT), ("druga", "druga", "DRUGA", MOD2_PORT)):
        (DRY / "modules" / folder).mkdir(parents=True, exist_ok=True)
        (DRY / "modules" / folder / "module.json").write_text(json.dumps({
            "format": 1, "id": mid, "button": button, "script": str(REPO / "tests" / "modules" / "dry_run_module.py"),
            "args": [MODULE], "port": port, "log_name": MODULE if mid == "proba" else "druga_log",
            "order": 1 if mid == "proba" else 2}, indent=2), encoding="utf-8")
    cfg = {
        "hub_port": HUB_PORT, "module": "proba", "modules_dir": str(DRY / "modules"), "control_port": CTL_PORT,
        "python_path": sys.executable, "module_dir": str(REPO / "modules" / MODULE), "module_ready_timeout_s": 90, "module_stop_grace_s": 10,
        "obs": {"enabled": True, "path": str(OBS_BIN / "obs-atrapa.exe"), "ws_port": OBS_PORT, "process_name": "obs-atrapa.exe", "ready_timeout_s": 20},
        "wol": {"enabled": False, "mac": "", "broadcast_addr": "255.255.255.255:9"},
        "state_file": str(DRY / "uslugi.json"),
    }
    (DRY / "hub.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def module_env():
    return {**os.environ, "BM_LOGS_DIR": str(LOGS), "DATABASE_URL": "sqlite:///" + DB.as_posix(),
            "BM_REQUIRED_PLUGINS": "timer-plugin,obs-ws-plugin", "PYTHONIOENCODING": "utf-8",
            "OBS_ATRAPA_PORT": str(OBS_PORT), "OBS_ATRAPA_LOG": str(DRY / "obs-atrapa.log")}


def start_hub(tag):
    out = open(DRY / f"hub-konsola-{tag}.txt", "wb")
    # Jak manager (E2d3c2): HUB zawsze z --module none, mimo "module": "proba" w konfiguracji
    pr = subprocess.Popen([str(DRY / "hub.exe"), "--config", str(DRY / "hub.json"), "--module", "none"], cwd=DRY / "hub", env=module_env(),
                          stdout=out, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    spawned.append(pr.pid)
    return pr


def active():
    return state().get("active")


def session_state():
    return state()["session"].get("state")


def remember_pids():
    try:
        st = status()
        for v in st.get("services", {}).values():
            if v.get("pid"):
                spawned.append(v["pid"])
        for v in st.get("plugin_manager", {}).get("local_plugins", {}).values():
            if v.get("pid"):
                spawned.append(v["pid"])
    except Exception:
        pass


def main():
    global DB
    for p in PORTS:
        if port_busy(p):
            sys.exit(f"Port {p} jest zajety (poprzednia proba nie posprzatala?). Niczego nie zabijam; sprawdz recznie.")
    r = subprocess.run([sys.executable, str(REPO / "tests" / "modules" / "prepare_dry_run.py"), MODULE], capture_output=True, text=True)
    if r.returncode:
        sys.exit("Przygotowanie bazy nie powiodlo sie:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    DB = REPO / "modules" / MODULE / "instance" / "database-proba.db"
    shutil.rmtree(LOGS, ignore_errors=True)
    shutil.rmtree(DRY / "timer-plugin" / "state", ignore_errors=True)
    (DRY / "uslugi.json").unlink(missing_ok=True)
    build()
    hub = manual = None
    try:
        say("== M1. HUB z --module none")
        hub = start_hub("1")
        up = wait_for(lambda: state()["protocol"] >= 1, 30)
        if not check("M1a kanal sterujacy odpowiada", up):
            return
        st = state()
        check("M1b /state: protokol 1 i commit z build", st["protocol"] == 1 and st["hub"]["commit"] == "dryrun", f"({st['protocol']}, {st['hub']['commit']})")
        check("M1c lista modulow z plikow module.json", [m["id"] for m in st["modules"]] == ["proba", "druga"], f"({st['modules']})")
        time.sleep(3)
        check("M1d HUB bez modulu mimo \"module\" w konfiguracji", active() is None and not port_busy(MOD_PORT) and "module" not in status().get("services", {}),
              f"(active={active()}, services={list(status().get('services', {}))})")
        hub_log = pathlib.Path(st["hub"]["hub_log"])     # sciezka z /state (tak bedzie ja czytal manager)
        check("M1g /state podaje istniejacy hub.log biezacego uruchomienia", hub_log.exists() and hub_log.parent.parent == LOGS, f"({hub_log})")
        head = hub_log.read_text(encoding="utf-8", errors="replace").splitlines()[:3]
        check("M1e pierwsze wiersze hub.log: brak modulu (argument) i wersja", "brak" in head[0] and "argument --module" in head[0]
              and any("Wersja HUB-a: commit dryrun, protokół kanału sterującego 1" in l for l in head), f"({head})")
        check("M1f kanal na wlasnym porcie, nie na porcie WebSocketu", port_busy(CTL_PORT) and port_busy(HUB_PORT))

        say("\n== M2. Start modulu kanalem sterujacym")
        code, res = ctl("POST", "/module/start", {"id": "proba"})
        check("M2a POST /module/start przyjety", code == 202 and res.get("ok"), f"({code} {res})")
        running = wait_for(lambda: (active() or {}).get("state") == "running", 120)
        check("M2b modul dziala (stan running, id proba)", running and active()["id"] == "proba", f"({active()})")
        check("M2c modul polaczony z HUB-em, HUB uruchomil timer-plugin",
              wait_for(lambda: status()["main_module_connected"] and "timer-plugin" in status()["connected_plugins"], 60), f"({status()['connected_plugins']})")
        check("M2d HUB zna status sesji od modulu (brak sesji)", wait_for(lambda: state()["session"]["known"] and session_state() == "none", 30), f"({state()['session']})")
        remember_pids()
        for _ in range(5):
            state()
        cp = status()["connected_plugins"]
        check("M2e manager nie jest liczony jako plugin ani modul", all("manager" not in k for k in cp) and len([k for k in cp]) <= 3, f"({cp})")
        if not SHORT:
            say("   czekam az modul i pluginy przepracuja 3 minuty...")
            end = time.time() + 420
            while time.time() < end:
                s = status()
                if s["services"]["module"].get("uptime_s", 0) >= 180 and \
                        min(p.get("uptime_s", 0) for p in s["plugin_manager"]["local_plugins"].values()) >= 180:
                    break
                time.sleep(5)
            s = status()
            mod = s["services"]["module"]
            local = s["plugin_manager"]["local_plugins"]
            timeouts = hub_log.read_text(encoding="utf-8", errors="replace").count("heartbeat timeout")
            ok = (mod["status"] == "online" and mod["restarts"] == 0 and mod.get("uptime_s", 0) >= 180
                  and all(p["status"] == "online" and p["restarts"] == 0 for p in local.values()) and timeouts == 0)
            check("M2f 3 minuty bez restartow (modul i pluginy)", ok,
                  f"(modul {mod['status']} restarts={mod['restarts']} uptime={mod.get('uptime_s')}; pluginy "
                  f"{ {k: (v['status'], v['restarts']) for k, v in local.items()} }; timeouty heartbeatu: {timeouts})")
        else:
            say("M2f POMINIETY (--krotka)")

        say("\n== M3. Wylacznosc i ochrona kanalu")
        code, res = ctl("POST", "/module/start", {"id": "druga"})
        check("M3a drugi modul odrzucony (409 busy)", code == 409 and res.get("reason") == "busy", f"({code} {res})")
        code, res = ctl("POST", "/module/start", {"id": "proba"})
        check("M3b ten sam modul drugi raz odrzucony", code == 409, f"({code} {res})")
        code, res = ctl("POST", "/module/start", {"id": "nie-ma"})
        check("M3c nieznany modul (404)", code == 404 and res.get("reason") == "unknown_module", f"({code} {res})")
        code, _ = ctl("GET", "/state", headers={"Origin": "http://localhost:8081"})
        check("M3d zadanie z naglowkiem Origin odrzucone (403)", code == 403, f"({code})")
        code, _ = ctl("POST", "/hub/stop", {}, headers={"Content-Type": "text/plain"})
        check("M3e POST bez application/json odrzucony (415)", code == 415 and hub.poll() is None, f"({code})")
        check("M3f po odmowach dziala nadal ten sam modul", (active() or {}).get("id") == "proba" and not port_busy(MOD2_PORT))

        say("\n== M4. Blokada przy otwartej sesji, zatrzymanie samego modulu")
        post(MOD + "/api/session/open")
        check("M4a sesja otwarta znana HUB-owi", wait_for(lambda: session_state() == "preparation", 20), f"({state()['session']})")
        code, res = ctl("POST", "/module/stop", {})
        check("M4b ZATRZYMAJ modul zablokowany", code == 409 and res.get("reason") == "session_open" and "Najpierw zamknij sesję transmisji" in res.get("error", ""),
              f"({code} {res})")
        code, res = ctl("POST", "/hub/stop", {})
        check("M4c ZATRZYMAJ HUB zablokowany", code == 409 and res.get("reason") == "session_open" and hub.poll() is None, f"({code} {res})")
        check("M4d modul dziala dalej", (active() or {}).get("state") == "running")
        post(MOD + "/api/session/close")
        check("M4e sesja zamknieta znana HUB-owi", wait_for(lambda: session_state() == "none", 20))
        remember_pids()
        before = status()
        obs_pid = before["services"].get("obs", {}).get("pid")
        plug_pids = {k: v.get("pid") for k, v in before["plugin_manager"]["local_plugins"].items()}
        code, res = ctl("POST", "/module/stop", {})
        check("M4f ZATRZYMAJ modul przyjety", code == 202, f"({code} {res})")
        check("M4g modul zatrzymany, port wolny", wait_for(lambda: active() is None and not port_busy(MOD_PORT), 30), f"({active()})")
        time.sleep(3)
        after = status()
        check("M4h HUB, OBS i pluginy zostaja (te same procesy)",
              hub.poll() is None and after["services"].get("obs", {}).get("pid") == obs_pid and obs_pid
              and {k: v.get("pid") for k, v in after["plugin_manager"]["local_plugins"].items()} == plug_pids,
              f"(obs {obs_pid}->{after['services'].get('obs', {}).get('pid')}, pluginy {plug_pids} -> "
              f"{ {k: v.get('pid') for k, v in after['plugin_manager']['local_plugins'].items()} })")
        last = state()["last_module"]
        check("M4i ostatni modul: proba, zatrzymany", last["id"] == "proba" and last["status"] == "stopped", f"({last})")
        code, res = ctl("POST", "/module/start", {"id": "proba"})
        again = code == 202 and wait_for(lambda: (active() or {}).get("state") == "running", 120)
        check("M4j ponowny start tego samego modulu", again, f"({code} {res}, {active()})")
        remember_pids()
        wait_for(lambda: state()["session"]["known"] and session_state() == "none", 20)   # sesja zamknieta w M4e
        ctl("POST", "/module/stop", {})
        wait_for(lambda: active() is None and not port_busy(MOD_PORT), 30)

        say("\n== M7. Modul uruchomiony recznie, poza HUB-em")
        env = {**module_env(), "BM_HUB_URL": f"ws://127.0.0.1:{HUB_PORT}/ws", "BM_MODULE_PORT": str(MOD_PORT)}
        manual = subprocess.Popen([sys.executable, str(REPO / "tests" / "modules" / "dry_run_module.py"), MODULE], cwd=REPO / "modules" / MODULE,
                                  env=env, stdout=open(DRY / "modul-reczny.txt", "wb"), stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        spawned.append(manual.pid)
        rec = wait_for(lambda: (active() or {}).get("state") == "manual", 120)
        a = active() or {}
        check("M7a modul reczny rozpoznany po nazwie z rejestracji", rec and a.get("id") == "proba" and a.get("name") == MODULE and a.get("pid") == 0, f"({a})")
        code, res = ctl("POST", "/module/start", {"id": "druga"})
        check("M7b start innego modulu zablokowany", code == 409 and res.get("reason") == "busy", f"({code} {res})")
        wait_for(lambda: state()["session"]["known"] and session_state() == "none", 30)
        code, res = ctl("POST", "/module/stop", {})
        check("M7c ZATRZYMAJ modul reczny przyjety", code == 202, f"({code} {res})")
        gone = wait_for(lambda: manual.poll() is not None, 30)
        check("M7d modul reczny zamknal sie sam (shutdown_module)", gone and manual.returncode == 0, f"(kod {manual.returncode})")
        check("M7e brak aktywnego modulu", wait_for(lambda: active() is None, 20), f"({active()})")

        say("\n== M8. Celowe zatrzymanie HUB-a kanalem")
        remember_pids()
        code, res = ctl("POST", "/hub/stop", {})
        check("M8a POST /hub/stop przyjety przy zamknietej sesji", code == 202, f"({code} {res})")
        check("M8b HUB zakonczyl sie sam", wait_for(lambda: hub.poll() is not None, 90), f"(kod {hub.poll()})")
        log_text = hub_log.read_text(encoding="utf-8", errors="replace")
        check("M8c w logu: zamkniecie zlecone przez kanal", "zlecone przez kanał sterujący" in log_text)
    finally:
        say("\n== M9. Sprzatanie")
        if hub is not None and hub.poll() is None:
            os.kill(hub.pid, signal.CTRL_BREAK_EVENT)
            wait_for(lambda: hub.poll() is not None, 60)
            if hub.poll() is None:
                subprocess.run(["taskkill", "/F", "/PID", str(hub.pid)], capture_output=True)
        for pid in set(spawned):
            if pid and pid_alive(pid):
                kill_tree(pid)
        stray = procs_under_dry()
        for pid in stray:
            kill_tree(pid)
        for port in PORTS:                              # porty testowe: proces, ktory je trzyma, jest z proby
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  f"Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ $_.OwningProcess }}"],
                                 capture_output=True, text=True).stdout
            for x in out.split():
                if x.isdigit():
                    kill_tree(int(x))
                    stray.append(int(x))
        time.sleep(1)
        left = [p for p in set(spawned) if p and pid_alive(p)] + stray
        ok = not left and not any(port_busy(p) for p in PORTS)
        check("M9 nic nie zostalo", ok, f"(zywe: {left}; zajete porty: {[p for p in PORTS if port_busy(p)]})")
        failed = [k for k, v in results.items() if not v]
        say(f"\nWYNIK: {'WSZYSTKO ZALICZONE' if not failed else 'NIEZALICZONE: ' + ', '.join(failed)}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print(f"(wynik zapisany w {OUT})")


if __name__ == "__main__":
    main()
