"""Proba z prawdziwym HUB-em, prawdziwym modulem i ATRAPA OBS (E2d2, scenariusze K1-K12). Prawdziwy OBS nie jest uzywany.

    modules\\.venv\\Scripts\\python.exe tests\\modules\\dry_run_hub_obs.py [futsal_nalf] [--krotka]

Buduje do wp-local/dryrun-hub-obs/: hub.exe, timer-plugin.exe, atrape OBS z oknami (hub/cmd/obs-atrapa, plik obs-atrapa.exe w katalogu
"obs-bin") i falszywy obs-ws-plugin (hub/cmd/fake-obs-plugin). Porty testowe: HUB 18090, modul 18091, "obs-websocket" atrapy 18455.
Wlasna konfiguracja HUB-a (--config), WoL wylaczony. Kazdy scenariusz sprzata po sobie po numerach procesow i po sciezce
(procesy z folderu proby), nigdy po nazwie obrazu.
  K1. Kolejnosc startu: HUB -> modul -> pluginy (timer, obs-ws) -> OBS; OBS z --disable-shutdown-check i katalogiem roboczym bin.
  K2. 3 minuty bez restartow (modul, OBS, pluginy).
  K3. HUB zabity silowo: modul i OBS zyja; nowy HUB je PRZEJMUJE (te same procesy), konczy pluginy-sieroty i uruchamia je od nowa.
  K4. Sesja otwarta, OBS pada: HUB uruchamia go ponownie, modul pokazuje pasek "OBS uruchomiony ponownie — wznow stream i nagrywanie".
  K5. Operator zamyka pasek.
  K6. Kolejne awarie: po 3 restartach HUB sie poddaje, modul pokazuje komunikat.
  K7. Zamkniecie HUB-a przy otwartej sesji: modul i OBS zostaja, pluginy sie zamykaja; nowy HUB przejmuje; martwy OBS przy otwartej sesji jest uruchamiany.
  K8. Sesja zamknieta, OBS pada: bez restartu.
  K9. Zamkniecie HUB-a przy zamknietej sesji: modul zamkniety, OBS zamkniety lagodnie (WM_CLOSE do okna glownego, doki nietkniete).
  K10. Stream trwa (falszywy plugin): zamkniecie HUB-a zostawia OBS; plugin milczy: tez zostawia.
  K11. OBS uruchomiony recznie jest "obcy": HUB go nie restartuje, nie zamyka, nie uruchamia drugiej kopii.
  K12. Sprzatanie: zadnego procesu z folderu proby, porty wolne.
--krotka pomija 3 minuty z K2.
"""
import json, os, pathlib, re, shutil, signal, socket, subprocess, sys, time, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SHORT = "--krotka" in sys.argv
MODULE = ARGS[0] if ARGS else "futsal_nalf"
DRY = REPO / "wp-local" / "dryrun-hub-obs"
LOGS = DRY / "logs"
OBS_BIN = DRY / "obs-bin"
OUT = REPO / "wp-local" / "tests-out" / "dry_run_hub_obs.txt"
HUB_PORT, MOD_PORT, OBS_PORT = 18090, 18091, 18455
HUB = f"http://127.0.0.1:{HUB_PORT}"
MOD = f"http://127.0.0.1:{MOD_PORT}"
ATRAPA_LOG = DRY / "obs-atrapa.log"
FAKE_STATE = DRY / "fake-obs-state.json"
FAKE_LOG = DRY / "fake-obs.log"
STATE_FILE = DRY / "uslugi.json"
RESTART_TEXT = "OBS uruchomiony ponownie — wznów stream i nagrywanie"
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


def wait_for(cond, timeout, step=0.4):
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


def post(url):
    req = urllib.request.Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode() or "{}")


def status():
    return get_json(HUB + "/status")


def svc(name):
    return status()["services"].get(name, {})


def pid_alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True, text=True).stdout
    return f'"{pid}"' in out


def kill_tree(pid):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def procs_under_dry():
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith('%s', 'OrdinalIgnoreCase') } "
          "| ForEach-Object { $_.ProcessId }" % str(DRY).replace("'", "''"))
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def set_fake(**kw):
    state = {"stream": False, "record": False, "silent": False, "fail": False}
    state.update(kw)
    FAKE_STATE.write_text(json.dumps(state), encoding="utf-8")


def notices():
    import socketio
    got = []
    c = socketio.Client()
    c.on("service_notices", lambda data: got.append(data))
    c.connect(MOD, transports=["websocket"])
    c.emit("get_service_notices")
    wait_for(lambda: bool(got), 5, 0.1)
    c.disconnect()
    return got[-1] if got else None


def dismiss(key):
    import socketio
    c = socketio.Client()
    c.connect(MOD, transports=["websocket"])
    c.emit("dismiss_service_notice", {"key": key})
    time.sleep(0.5)
    c.disconnect()


def run_dir():
    dirs = sorted(d for d in LOGS.iterdir() if d.is_dir() and d.name.startswith("logs-"))
    return dirs[-1] if dirs else None


def hub_log():
    d = run_dir()
    return (d / "hub.log").read_text(encoding="utf-8", errors="replace") if d else ""


def atrapa_log():
    return ATRAPA_LOG.read_text(encoding="utf-8", errors="replace") if ATRAPA_LOG.exists() else ""


def build():
    DRY.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    OBS_BIN.mkdir(exist_ok=True)
    targets = (("hub.exe", REPO / "hub", ".", DRY), ("timer-plugin.exe", REPO / "plugins" / "timer-plugin", "./cmd/timer-plugin", DRY),
               ("obs-atrapa.exe", REPO / "hub", "./cmd/obs-atrapa", OBS_BIN), ("fake-obs-plugin.exe", REPO / "hub", "./cmd/fake-obs-plugin", DRY))
    for name, cwd, target, outdir in targets:
        r = subprocess.run(["go", "build", "-o", str(outdir / name), target], cwd=cwd, capture_output=True, text=True)
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
                          "working_dir": str(DRY), "env": ["PLUGIN_ID=obs-ws-plugin", f"FAKE_OBS_STATE={FAKE_STATE}", f"FAKE_OBS_LOG={FAKE_LOG}"]},
    }
    (DRY / "hub" / "config" / "plugins.json").write_text(json.dumps(plugins, indent=2), encoding="utf-8")
    (DRY / "hub" / "config" / "overlays.json").write_text("{}", encoding="utf-8")
    cfg = {
        "hub_port": HUB_PORT, "module": "proba",
        "modules": {"proba": {"script": str(REPO / "tests" / "modules" / "dry_run_module.py"), "args": [MODULE], "port": MOD_PORT, "log_name": MODULE}},
        "python_path": sys.executable, "module_dir": str(REPO / "modules" / MODULE), "module_ready_timeout_s": 90, "module_stop_grace_s": 10,
        "obs": {"enabled": True, "path": str(OBS_BIN / "obs-atrapa.exe"), "ws_port": OBS_PORT, "process_name": "obs-atrapa.exe", "ready_timeout_s": 20},
        "wol": {"enabled": False, "mac": "", "broadcast_addr": "255.255.255.255:9"},
        "state_file": str(STATE_FILE),
    }
    (DRY / "hub.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def start_hub(tag):
    env = {**os.environ, "BM_LOGS_DIR": str(LOGS), "DATABASE_URL": "sqlite:///" + DB.as_posix(), "BM_REQUIRED_PLUGINS": "timer-plugin,obs-ws-plugin",
           "PYTHONIOENCODING": "utf-8", "OBS_ATRAPA_PORT": str(OBS_PORT), "OBS_ATRAPA_LOG": str(ATRAPA_LOG)}
    out = open(DRY / f"hub-konsola-{tag}.txt", "wb")
    pr = subprocess.Popen([str(DRY / "hub.exe"), "--config", str(DRY / "hub.json")], cwd=DRY / "hub", env=env,
                          stdout=out, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    spawned.append(pr.pid)
    return pr


def hard_kill(pr):
    subprocess.run(["taskkill", "/F", "/PID", str(pr.pid)], capture_output=True)
    pr.wait()


def graceful_stop(pr, timeout=90):
    os.kill(pr.pid, signal.CTRL_BREAK_EVENT)
    return wait_for(lambda: pr.poll() is not None, timeout)


def all_up(timeout=120):
    return wait_for(lambda: svc("module").get("status") == "online" and svc("obs").get("status") == "online"
                    and {"timer-plugin", "obs-ws-plugin"} <= set(status()["connected_plugins"]), timeout)


def session_state():
    return status().get("session", {}).get("state")


def open_session():
    post(MOD + "/api/session/open")
    return wait_for(lambda: session_state() == "preparation", 20)


def close_session():
    post(MOD + "/api/session/close")
    return wait_for(lambda: session_state() == "none", 20)


def pids():
    s = status()
    return {"module": s["services"]["module"].get("pid"), "obs": s["services"]["obs"].get("pid"),
            "timer": s["plugin_manager"]["local_plugins"]["timer-plugin"].get("pid"),
            "fake": s["plugin_manager"]["local_plugins"]["obs-ws-plugin"].get("pid")}


def main():
    global DB
    for p in (HUB_PORT, MOD_PORT, OBS_PORT):
        if port_busy(p):
            sys.exit(f"Port {p} jest zajety (poprzednia proba nie posprzatala?). Niczego nie zabijam; sprawdz recznie.")
    r = subprocess.run([sys.executable, str(REPO / "tests" / "modules" / "prepare_dry_run.py"), MODULE], capture_output=True, text=True)
    if r.returncode:
        sys.exit("Przygotowanie bazy nie powiodlo sie:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    DB = REPO / "modules" / MODULE / "instance" / "database-proba.db"
    shutil.rmtree(LOGS, ignore_errors=True)
    for f in (STATE_FILE, ATRAPA_LOG, FAKE_LOG):
        f.unlink(missing_ok=True)
    shutil.rmtree(DRY / "timer-plugin" / "state", ignore_errors=True)
    build()
    set_fake()
    hub = None
    try:
        say("== K1. Kolejnosc startu")
        hub = start_hub("1")
        if not check("K1a wszystko wstalo (modul, OBS, pluginy)", all_up(), f"({ {k: v.get('status') for k, v in status()['services'].items()} })"):
            return
        log = hub_log()
        i_mod, i_plugin, i_obs = log.find("Usługa module gotowa"), log.find("Plugin registered: obs-ws-plugin"), log.find("Usługa obs uruchomiona")
        check("K1b kolejnosc: modul gotowy, potem obs-ws-plugin, potem OBS", 0 <= i_mod < i_plugin < i_obs, f"({i_mod} < {i_plugin} < {i_obs})")
        a = atrapa_log()
        check("K1c OBS z --disable-shutdown-check i katalogiem roboczym bin", "--disable-shutdown-check" in a and f"cwd={OBS_BIN}" in a, f"({a.strip()[:200]})")
        s = svc("obs")
        check("K1d OBS uruchomiony przez HUB (nie obcy)", s.get("status") == "online" and not s.get("external") and s.get("pid", 0) > 0, f"({s})")
        spawned.extend(v for v in pids().values() if v)
        ids1 = pids()

        if not SHORT:
            say("\n== K2. 3 minuty bez restartow")
            wait_for(lambda: svc("obs").get("uptime_s", 0) >= 180 and svc("module").get("uptime_s", 0) >= 180, 420, 5)
            st = status()
            ok = (all(st["services"][k]["restarts"] == 0 and st["services"][k]["status"] == "online" for k in ("module", "obs"))
                  and all(p["restarts"] == 0 and p["status"] == "online" for p in st["plugin_manager"]["local_plugins"].values())
                  and hub_log().count("heartbeat timeout") == 0)
            check("K2 3 minuty bez restartow", ok, f"(OBS uptime={st['services']['obs'].get('uptime_s')} s, modul={st['services']['module'].get('uptime_s')} s)")
        else:
            say("K2 POMINIETY (--krotka)")

        say("\n== K3. HUB zabity silowo: przejecie modulu i OBS, sieroty pluginow")
        hard_kill(hub)
        time.sleep(3)
        check("K3a modul i OBS zyja po zabiciu HUB-a", pid_alive(ids1["module"]) and pid_alive(ids1["obs"]))
        check("K3b pluginy zostaly sierotami", pid_alive(ids1["timer"]) and pid_alive(ids1["fake"]))
        hub = start_hub("2")
        ok = wait_for(lambda: svc("module").get("adopted") and svc("obs").get("adopted"), 40)
        ids2 = pids() if ok else {}
        check("K3c nowy HUB przejmuje modul i OBS (te same procesy)", ok and ids2["module"] == ids1["module"] and ids2["obs"] == ids1["obs"], f"({ids2})")
        check("K3d przejety OBS i modul gotowe", all_up(60))
        check("K3e sieroty pluginow zakonczone, uruchomione nowe",
              wait_for(lambda: not pid_alive(ids1["timer"]) and not pid_alive(ids1["fake"]), 30)
              and pids()["timer"] not in (None, ids1["timer"]) and pids()["fake"] not in (None, ids1["fake"]))
        spawned.extend(v for v in pids().values() if v)
        check("K3f hub.log: przejecie OBS i folder logow", "Przejęto usługę obs" in hub_log() and "Przejęto usługę module" in hub_log())

        say("\n== K4. Sesja otwarta, OBS pada: restart i pasek")
        check("K4a sesja otwarta (przygotowanie) znana HUB-owi", open_session())
        obs_pid = svc("obs")["pid"]
        kill_tree(obs_pid)
        ok = wait_for(lambda: svc("obs").get("status") == "online" and svc("obs").get("pid") not in (None, 0, obs_pid), 60)
        check("K4b OBS uruchomiony ponownie przez HUB", ok, f"({svc('obs')})")
        spawned.append(svc("obs").get("pid", 0))
        n = notices() or []
        check("K4c pasek: OBS uruchomiony ponownie — wznów stream i nagrywanie",
              any(x["key"] == "obs-restarted" and x["text"] == RESTART_TEXT for x in n), f"({n})")
        n2 = notices() or []
        check("K4d pasek zostaje po odswiezeniu panelu (ponowne pobranie listy)", any(x["key"] == "obs-restarted" for x in n2))

        say("\n== K5. Operator zamyka pasek")
        dismiss("obs-restarted")
        check("K5 pasek zniknal", not any(x["key"] == "obs-restarted" for x in (notices() or [])))

        say("\n== K6. Po 3 restartach HUB sie poddaje")
        for i in range(3):
            wait_for(lambda: svc("obs").get("status") == "online", 60)
            old = svc("obs")["pid"]
            kill_tree(old)
            if i < 2:
                wait_for(lambda: svc("obs").get("status") == "online" and svc("obs").get("pid") not in (None, 0, old), 60)
        gave_up = wait_for(lambda: any(x["key"] == "obs-gave-up" for x in (notices() or [])), 60)
        s = svc("obs")
        check("K6 limit wyczerpany: HUB nie uruchamia OBS, modul dostaje komunikat", gave_up and s.get("status") == "error" and s.get("restarts") == 3, f"({s})")

        say("\n== K7. Zamkniecie HUB-a przy otwartej sesji")
        ids3 = {"module": svc("module")["pid"], "timer": pids()["timer"], "fake": pids()["fake"]}
        check("K7a HUB zakonczyl sie po Ctrl+Break", graceful_stop(hub))
        time.sleep(1)
        check("K7b modul zostaje uruchomiony mimo zamkniecia HUB-a", pid_alive(ids3["module"]) and port_busy(MOD_PORT))
        check("K7c pluginy lokalne zatrzymane", not pid_alive(ids3["timer"]) and not pid_alive(ids3["fake"]))
        st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        kinds = sorted((e["kind"], e["id"]) for e in st["entries"])
        check("K7d plik stanu opisuje dzialajacy modul i sesje", ("service", "module") in kinds and not any(k == "plugin" for k, _ in kinds)
              and st.get("session", {}).get("state") == "preparation", f"({kinds}, {st.get('session')})")
        hub = start_hub("3")
        check("K7e nowy HUB przejmuje modul", wait_for(lambda: svc("module").get("adopted") and svc("module").get("pid") == ids3["module"], 40))
        started = wait_for(lambda: svc("obs").get("status") == "online" and svc("obs").get("pid", 0) > 0, 60)
        check("K7f OBS martwy przy otwartej sesji (HUB nie dzialal): uruchomiony na starcie", started, f"({svc('obs')})")
        spawned.extend(v for v in pids().values() if v)

        say("\n== K8. Sesja zamknieta, OBS pada: bez restartu")
        check("K8a sesja zamknieta znana HUB-owi", close_session())
        obs_pid = svc("obs")["pid"]
        kill_tree(obs_pid)
        time.sleep(8)
        s = svc("obs")
        check("K8b OBS nie zostal uruchomiony ponownie", s.get("pid", 0) in (0, None) and s.get("restarts", 0) == 0 and not port_busy(OBS_PORT), f"({s})")

        say("\n== K9. Zamkniecie HUB-a przy zamknietej sesji: moduł zamkniety, OBS (uruchomiony przez HUB) lagodnie")
        # przywracamy OBS: restart HUB-a przy zamknietej sesji uruchamia OBS od nowa (wpis w pliku stanu usuniety po zamknieciu modulu)
        check("K9a HUB zamkniety (sesja zamknieta: modul zamykany)", graceful_stop(hub))
        time.sleep(1)
        check("K9b modul zamkniety, port wolny", not port_busy(MOD_PORT))
        hub = start_hub("4")
        check("K9c po starcie wszystko dziala", all_up(120))
        spawned.extend(v for v in pids().values() if v)
        ids4 = pids()
        n_before = atrapa_log().count("main-got-close")
        check("K9d HUB zakonczony Ctrl+Break przy zamknietej sesji i bezczynnym OBS", graceful_stop(hub))
        time.sleep(1)
        a = atrapa_log()
        check("K9e OBS zamkniety lagodnie: okno glowne dostalo WM_CLOSE, doki nie", a.count("main-got-close") == n_before + 1 and "dock-got-close" not in a, f"({a.strip()[-200:]})")
        check("K9f OBS i modul zakonczone, porty wolne", not pid_alive(ids4["obs"]) and not pid_alive(ids4["module"]) and not port_busy(OBS_PORT) and not port_busy(MOD_PORT))
        check("K9g plik stanu bez wpisow zatrzymanych uslug", not json.loads(STATE_FILE.read_text(encoding="utf-8"))["entries"])

        say("\n== K10. Stream trwa albo plugin milczy: OBS zostaje")
        for tag, fake in (("stream", {"stream": True}), ("milczy", {"silent": True})):
            hub = start_hub(f"5-{tag}")
            all_up(120)
            spawned.extend(v for v in pids().values() if v)
            obs_pid, mod_pid = svc("obs")["pid"], svc("module")["pid"]
            if tag == "milczy":
                check("K10 (milczy) OBS z poprzedniego obiegu przejety przez nowy HUB", svc("obs").get("adopted") is True, f"({svc('obs')})")
            set_fake(**fake)
            t0 = time.time()
            graceful_stop(hub)
            check(f"K10 ({tag}) OBS zostaje uruchomiony, modul zatrzymany", pid_alive(obs_pid) and not pid_alive(mod_pid),
                  f"(zamykanie {time.time() - t0:.1f} s)")
            check(f"K10 ({tag}) OBS nie dostal prosby o zamkniecie", atrapa_log().count("main-got-close") == n_before + 1)
            set_fake()
            if tag == "stream":
                continue                                 # OBS zostaje do nastepnego obiegu: nowy HUB go przejmie
        kill_tree(obs_pid)                               # sprzatanie OBS zostawionego przez HUB
        wait_for(lambda: not port_busy(OBS_PORT), 15)
        STATE_FILE.unlink(missing_ok=True)               # K11 zaczyna bez starego pliku stanu

        say("\n== K11. OBS uruchomiony recznie jest obcy")
        env = {**os.environ, "OBS_ATRAPA_PORT": str(OBS_PORT), "OBS_ATRAPA_LOG": str(ATRAPA_LOG)}
        manual = subprocess.Popen([str(OBS_BIN / "obs-atrapa.exe")], cwd=OBS_BIN, env=env)
        spawned.append(manual.pid)
        wait_for(lambda: port_busy(OBS_PORT), 20)
        hub = start_hub("6")
        ok = wait_for(lambda: svc("obs").get("status") == "external", 60)
        spawned.append(svc("module").get("pid", 0))
        check("K11a HUB widzi obcy OBS i nie uruchamia drugiej kopii", ok and svc("obs").get("pid") == 0, f"({svc('obs')})")
        kill_tree(manual.pid)                            # obcy OBS pada: HUB go nie wskrzesza
        open_session()
        time.sleep(8)
        check("K11b obcy OBS po awarii nie jest uruchamiany przez HUB", not port_busy(OBS_PORT))
        graceful_stop(hub)
    finally:
        say("\n== K12. Sprzatanie")
        if hub is not None and hub.poll() is None:
            subprocess.run(["taskkill", "/F", "/PID", str(hub.pid)], capture_output=True)
        for pid in set(spawned):
            if pid and pid_alive(pid):
                kill_tree(pid)
        stray = procs_under_dry()
        for pid in stray:
            kill_tree(pid)
        for port in (MOD_PORT, OBS_PORT, HUB_PORT):      # porty testowe: proces, ktory je trzyma, jest z proby
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  f"Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ $_.OwningProcess }}"],
                                 capture_output=True, text=True).stdout
            for x in out.split():
                if x.isdigit():
                    kill_tree(int(x))
                    stray.append(int(x))
        time.sleep(1)
        left = [p for p in set(spawned) if p and pid_alive(p)] + stray
        ok = not left and not any(port_busy(p) for p in (HUB_PORT, MOD_PORT, OBS_PORT))
        results["K12 nic nie zostalo"] = ok
        say(f"K12 nic nie zostalo: {'ZALICZONY' if ok else 'NIEZALICZONY'} (zywe: {left}; zajete porty: "
            f"{[p for p in (HUB_PORT, MOD_PORT, OBS_PORT) if port_busy(p)]})")
        failed = [k for k, v in results.items() if not v]
        say(f"\nWYNIK: {'WSZYSTKO ZALICZONE' if not failed else 'NIEZALICZONE: ' + ', '.join(failed)}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print(f"(wynik zapisany w {OUT})")


if __name__ == "__main__":
    main()
