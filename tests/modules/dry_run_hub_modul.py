"""Proba z prawdziwym HUB-em, ktory SAM uruchamia modul (E2d1, scenariusze J1-J5).

    modules\\.venv\\Scripts\\python.exe tests\\modules\\dry_run_hub_modul.py [futsal_nalf] [--krotka]

Buduje swiezo hub i timer-plugin do wp-local/dryrun-hub/ (nie rusza plikow .exe w repo), uzywa WLASNEJ konfiguracji HUB-a
(--config) i portow testowych 18080 (HUB) / 18081 (modul), wiec nie koliduje z wersja transmisyjna (8080/8081).
Baza: kopia lokalnej bazy (prepare_dry_run.py). Modul to dry_run_module.py (bez kopiowania plikow do overlayow).
  J1. HUB uruchamia modul (proces odlaczony); pierwszy wiersz hub.log: modul i zrodlo; modul laczy sie z HUB-em,
      HUB uruchamia timer-plugin na deklaracje modulu; logi modulu w jednym pliku bez dublowania wierszy; karty przegladarki
      (klient socket.io) otwierane i zamykane nie zostawiaja tracebackow w wyjscie.log; zalegle polecenie zegara bez sesji
      jest odrzucone; konsola HUB-a pokazuje kazdy wiersz modulu raz.
  J2. (stala zasada prob) 3 minuty bez restartow: modul i pluginy lokalne maja restarts == 0, brak timeoutow heartbeatu.
  J3. HUB zabity silowo: modul zyje dalej i odpowiada (przezywa awarie HUB-a); nowy HUB PRZEJMUJE dzialajacy modul
      (plik stanu: numer i czas utworzenia procesu) zamiast uruchamiac drugi, konczy plugin-sierote i dostaje status sesji.
  J4. Lagodne zamkniecie HUB-a (Ctrl+Break): modul dostaje shutdown_module i zamyka sie sam, port modulu wolny, plugin zatrzymany.
  J5. Sprzatanie: zadnego procesu uruchomionego przez probe nie zostaje (sprawdzane po numerach procesow, nigdy po nazwie obrazu).
--krotka pomija 3 minuty z J2 (do szybkich sprawdzen; wynik J2 jest wtedy oznaczony jako POMINIETY).
Wymaga wolnych portow 18080 i 18081.
"""
import json, os, pathlib, re, shutil, signal, socket, subprocess, sys, time, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SHORT = "--krotka" in sys.argv
MODULE = ARGS[0] if ARGS else "futsal_nalf"
DRY = REPO / "wp-local" / "dryrun-hub"
LOGS = DRY / "logs"
OUT = REPO / "wp-local" / "tests-out" / "dry_run_hub_modul.txt"
HUB_PORT, MOD_PORT = 18080, 18081
HUB = f"http://127.0.0.1:{HUB_PORT}"
MOD = f"http://127.0.0.1:{MOD_PORT}"
lines = []
results = {}
spawned = []                                   # numery procesow uruchomionych przez probe (do sprzatania)


def say(msg=""):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode(), flush=True)
    lines.append(msg)


def port_busy(p):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", p)) == 0


def get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def status():
    return get_json(HUB + "/status")


def pid_alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def kill_pid_tree(pid):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


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


FLASK_LOG_LINE = re.compile(r"^\[\d{4}-\d\d-\d\d [\d:,]+\] (DEBUG|INFO|WARNING|ERROR|CRITICAL) in ", re.M)


def wyjscie_ok(path):
    """Surowe wyjscie procesu nie ma tracebackow ani wierszy logu (format Flaska)."""
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    return "Traceback" not in text and not FLASK_LOG_LINE.search(text)


def wyjscie_summary(path):
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    return f"{len(text)} B, wierszy {len(text.splitlines())}, tracebackow {text.count('Traceback')}, wierszy w formacie logu {len(FLASK_LOG_LINE.findall(text))}"


def procs_under_dry():
    """Numery procesow, ktorych plik wykonywalny lezy w folderze proby (wp-local/dryrun-hub): sprawdzanie po SCIEZCE, nie po nazwie obrazu."""
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith('%s', 'OrdinalIgnoreCase') } "
          "| ForEach-Object { $_.ProcessId }" % str(DRY).replace("'", "''"))
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def build():
    DRY.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    for name, cwd, target in (("hub.exe", REPO / "hub", "."), ("timer-plugin.exe", REPO / "plugins" / "timer-plugin", "./cmd/timer-plugin")):
        r = subprocess.run(["go", "build", "-o", str(DRY / name), target], cwd=cwd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"Budowanie {name} nie powiodlo sie:\n{r.stderr}")
    (DRY / "hub" / "config").mkdir(parents=True, exist_ok=True)
    (DRY / "timer-plugin").mkdir(exist_ok=True)
    shutil.copy(REPO / "plugins" / "timer-plugin" / "config.json", DRY / "timer-plugin" / "config.json")
    plugins = {"timer-plugin": {
        "id": "timer-plugin", "name": "Timer Plugin", "type": "local",
        "executable_path": str(DRY / "timer-plugin.exe"), "working_dir": str(DRY / "timer-plugin"), "args": [],
        "env": ["PLUGIN_ID=timer-plugin"],            # HUB_URL dopisuje sam HUB wedlug swojego portu
        "auto_start": True, "restart_on_crash": True, "max_restarts": 10, "restart_delay_ms": 3000, "startup_delay_ms": 1000,
        "health_check_interval": 10, "is_critical": False}}
    (DRY / "hub" / "config" / "plugins.json").write_text(json.dumps(plugins, indent=2), encoding="utf-8")
    (DRY / "hub" / "config" / "overlays.json").write_text("{}", encoding="utf-8")
    hub_cfg = {
        "hub_port": HUB_PORT, "module": "proba",
        "modules": {"proba": {"script": str(REPO / "tests" / "modules" / "dry_run_module.py"), "args": [MODULE],
                              "port": MOD_PORT, "log_name": MODULE}},
        "python_path": sys.executable, "module_dir": str(REPO / "modules" / MODULE),
        "module_ready_timeout_s": 90, "module_stop_grace_s": 10,
        "wol": {"enabled": False, "mac": "", "broadcast_addr": "255.255.255.255:9"},   # w probach nigdy nie wysylamy WoL
        "state_file": str(DRY / "uslugi.json"),        # plik stanu proby (nie run/ z repozytorium)
        "obs": {"enabled": False, "path": "", "ws_port": 0, "process_name": ""},      # OBS w probach: wylaczony
    }
    (DRY / "hub.json").write_text(json.dumps(hub_cfg, indent=2), encoding="utf-8")


def start_hub(tag):
    env = {**os.environ, "BM_LOGS_DIR": str(LOGS), "DATABASE_URL": "sqlite:///" + DB.as_posix(),
           "BM_REQUIRED_PLUGINS": "timer-plugin", "PYTHONIOENCODING": "utf-8"}
    out = open(DRY / f"hub-konsola-{tag}.txt", "wb")
    pr = subprocess.Popen([str(DRY / "hub.exe"), "--config", str(DRY / "hub.json")], cwd=DRY / "hub", env=env,
                          stdout=out, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    spawned.append(pr.pid)
    return pr


def run_dir():
    dirs = sorted(d for d in LOGS.iterdir() if d.is_dir() and d.name.startswith("logs-"))
    return dirs[-1] if dirs else None


def check(name, ok, detail=""):
    results[name] = ok
    say(f"{name}: {'ZALICZONY' if ok else 'NIEZALICZONY'} {detail}")
    return ok


def main():
    global DB
    for p in (HUB_PORT, MOD_PORT):
        if port_busy(p):
            sys.exit(f"Port {p} jest zajety (poprzednia proba nie posprzatala?). Niczego nie zabijam; sprawdz recznie.")
    r = subprocess.run([sys.executable, str(REPO / "tests" / "modules" / "prepare_dry_run.py"), MODULE], capture_output=True, text=True)
    if r.returncode:
        sys.exit("Przygotowanie bazy nie powiodlo sie:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    DB = REPO / "modules" / MODULE / "instance" / "database-proba.db"
    shutil.rmtree(DRY / "logs", ignore_errors=True)
    shutil.rmtree(DRY / "timer-plugin" / "state", ignore_errors=True)
    build()
    hub = module_pid = plugin_pid = None
    try:
        say("== J1. HUB uruchamia modul")
        hub = start_hub("1")
        ready = wait_for(lambda: status()["services"]["module"]["status"] == "online", 120)
        if not check("J1a modul uruchomiony przez HUB i gotowy", ready, ""):
            return
        st = status()
        module_pid = st["services"]["module"]["pid"]
        spawned.append(module_pid)
        rd = run_dir()
        first = (rd / "hub.log").read_text(encoding="utf-8", errors="replace").splitlines()[0]
        check("J1b pierwszy wiersz hub.log podaje modul (nazwe pliku logu) i zrodlo", f"Moduł: proba ({MODULE}) (źródło: hub.json)" in first, repr(first))
        check("J1c modul polaczony z HUB-em", wait_for(lambda: status()["main_module_connected"], 30))
        got_plugin = wait_for(lambda: "timer-plugin" in status()["connected_plugins"], 60)
        check("J1d HUB uruchomil timer-plugin na deklaracje modulu", got_plugin)
        if got_plugin:
            plugin_pid = status()["plugin_manager"]["local_plugins"]["timer-plugin"]["pid"]
            spawned.append(plugin_pid)
        mod_log = rd / f"modul-{MODULE}.log"
        text = mod_log.read_text(encoding="utf-8", errors="replace") if mod_log.exists() else ""
        # wiersze-separatory ("====") z tej samej milisekundy nie sa dublami
        rows = [l for l in text.splitlines() if l.strip() and not l.rstrip().endswith("=====")]
        dup = len(rows) - len(set(rows))
        check("J1e jeden plik logu modulu, wiersze bez dublowania", mod_log.exists() and len(rows) > 3 and dup == 0,
              f"(wierszy {len(rows)}, powtorzonych {dup}, pliki: {sorted(p.name for p in rd.iterdir())})")
        out_file = rd / f"modul-{MODULE}.wyjscie.log"
        check("J1f surowe wyjscie modulu w osobnym pliku", out_file.exists())
        try:
            urllib.request.urlopen(MOD + "/api/session", timeout=10).read()
            check("J1g strona modulu odpowiada", True)
        except Exception as e:
            check("J1g strona modulu odpowiada", False, str(e))

        import socketio as sio
        for _ in range(3):                             # karty przegladarki otwierane i zamykane (dawniej: ConnectionError w wyjscie.log)
            c = sio.Client()
            c.connect(MOD, transports=["websocket"])
            time.sleep(0.4)
            c.disconnect()
            time.sleep(0.4)
        c = sio.Client()                               # zalegle polecenie ze starej karty, bez otwartej sesji
        c.connect(MOD, transports=["websocket"])
        c.emit("timer_start", {"timer_id": "OPPxBRO p:1"})
        time.sleep(1.0)
        c.disconnect()
        time.sleep(0.5)
        text = mod_log.read_text(encoding="utf-8", errors="replace")
        check("J1h zalegle polecenie zegara bez sesji odrzucone (wpis w logu, zegar nie ruszyl)",
              "Odrzucono zdarzenie timer_start: brak otwartej sesji" in text and "Started timer: OPPxBRO" not in text)
        rd1 = rd
        sess = status().get("session", {})
        check("J1k HUB zna status sesji zgloszony przez modul (brak sesji po starcie)", sess.get("known") is True and sess.get("state") == "none", f"({sess})")
        check("J1i wyjscie.log po otwieraniu i zamykaniu kart: bez tracebackow i wierszy w formacie logu", wyjscie_ok(out_file),
              f"({wyjscie_summary(out_file)})")
        console = (DRY / "hub-konsola-1.txt").read_text(encoding="utf-8", errors="replace")
        modul_lines = [l for l in console.splitlines() if l.startswith("[moduł]") and not l.rstrip().endswith("=====")]
        dup_console = len(modul_lines) - len(set(modul_lines))
        check("J1j konsola HUB-a: wiersze modulu bez powtorzen, bez tracebackow", dup_console == 0 and "Traceback" not in console and len(modul_lines) > 3,
              f"(wierszy modulu {len(modul_lines)}, powtorzonych {dup_console})")

        if not SHORT:
            say("\n== J2. Stabilnosc: 3 minuty bez restartow")
            end = time.time() + 420
            while time.time() < end:
                st = status()
                if st["services"]["module"].get("uptime_s", 0) >= 180 and \
                        min(p.get("uptime_s", 0) for p in st["plugin_manager"]["local_plugins"].values()) >= 180:
                    break
                time.sleep(5)
            st = status()
            mod = st["services"]["module"]
            local = st["plugin_manager"]["local_plugins"]
            hub_log = (rd / "hub.log").read_text(encoding="utf-8", errors="replace")
            timeouts = hub_log.count("heartbeat timeout")
            ok = (mod["status"] == "online" and mod["restarts"] == 0 and mod.get("uptime_s", 0) >= 180
                  and all(p["status"] == "online" and p["restarts"] == 0 for p in local.values()) and timeouts == 0)
            check("J2 3 minuty bez restartow (modul i pluginy)", ok,
                  f"(modul {mod['status']} restarts={mod['restarts']} uptime={mod.get('uptime_s')} s; pluginy "
                  f"{ {k: (v['status'], v['restarts']) for k, v in local.items()} }; timeouty heartbeatu: {timeouts})")
        else:
            say("J2 POMINIETY (--krotka)")

        say("\n== J3. HUB zabity silowo: modul przezywa, nowy HUB nie uruchamia drugiej kopii")
        subprocess.run(["taskkill", "/F", "/PID", str(hub.pid)], capture_output=True)
        hub.wait()
        time.sleep(3)
        alive_ok = pid_alive(module_pid)
        try:
            urllib.request.urlopen(MOD + "/api/session", timeout=10).read()
            responds = True
        except Exception:
            responds = False
        check("J3a modul zyje i odpowiada po zabiciu HUB-a", alive_ok and responds, f"(pid {module_pid})")
        orphan_alive_before = bool(plugin_pid) and pid_alive(plugin_pid)
        hub = start_hub("2")
        adopted = wait_for(lambda: status()["services"]["module"].get("adopted") is True, 30)
        st = status()
        mod2 = st["services"]["module"]
        check("J3b nowy HUB przejmuje dzialajacy modul (ten sam proces, bez drugiej kopii)",
              adopted and mod2["pid"] == module_pid and pid_alive(module_pid), f"({mod2})")
        check("J3b2 przejety modul jest gotowy", wait_for(lambda: status()["services"]["module"]["status"] == "online", 30))
        hub2_log = (run_dir() / "hub.log").read_text(encoding="utf-8", errors="replace")
        check("J3b3 w hub.log: przejecie i folder logow modulu", "Przejęto usługę module" in hub2_log and "Logi usługi module prowadzone w folderze" in hub2_log
              and str(rd).split("\\")[-1] in hub2_log)
        check("J3f plugin-sierota z poprzedniego HUB-a zakonczony przez nowy HUB (po numerze i czasie utworzenia)",
              orphan_alive_before and wait_for(lambda: not pid_alive(plugin_pid), 20), f"(PID {plugin_pid})")
        # drugi HUB uruchamia timer-plugin na deklaracje modulu; po zabiciu HUB-a plugin zostaje sierota (kończy ją dopiero E2d2: plik stanu)
        wait_for(lambda: status()["plugin_manager"]["local_plugins"].get("timer-plugin", {}).get("pid", 0) > 0, 30)
        plugin2_pid = status()["plugin_manager"]["local_plugins"].get("timer-plugin", {}).get("pid", 0)
        if plugin2_pid:
            spawned.append(plugin2_pid)
        sess2 = wait_for(lambda: status()["session"]["known"] is True and status()["session"]["from_file"] is False, 60)
        check("J3e nowy HUB dostaje status sesji od modulu po ponownym polaczeniu (bez restartu modulu)", sess2, f"({status().get('session')})")
        subprocess.run(["taskkill", "/F", "/PID", str(hub.pid)], capture_output=True)
        hub.wait()
        if plugin2_pid:
            kill_pid_tree(plugin2_pid)
        kill_pid_tree(module_pid)
        check("J3c po sprzataniu port modulu wolny", wait_for(lambda: not port_busy(MOD_PORT), 15))
        check("J3d wyjscie.log modulu z J1 po zabiciu HUB-a: bez tracebackow i wierszy w formacie logu", wyjscie_ok(out_file),
              f"({wyjscie_summary(out_file)})")

        say("\n== J4. Lagodne zamkniecie HUB-a: modul zamyka sie sam")
        hub = start_hub("3")
        wait_for(lambda: status()["services"]["module"]["status"] == "online", 120)
        module_pid = status()["services"]["module"]["pid"]
        spawned.append(module_pid)
        wait_for(lambda: "timer-plugin" in status()["connected_plugins"], 60)
        plugin_pid = status()["plugin_manager"]["local_plugins"]["timer-plugin"]["pid"]
        spawned.append(plugin_pid)
        import socketio as sio4
        panel = sio4.Client()                          # wczytanie panelu: get_record_status (dawniej recording_command do wszystkich pluginow)
        panel.connect(MOD, transports=["websocket"])
        panel.emit("get_record_status")
        time.sleep(1.5)
        panel.disconnect()
        os.kill(hub.pid, signal.CTRL_BREAK_EVENT)
        exited = wait_for(lambda: hub.poll() is not None, 60)
        check("J4a HUB zakonczyl sie po Ctrl+Break", exited)
        check("J4b modul zamkniety, port wolny", not pid_alive(module_pid) and not port_busy(MOD_PORT),
              f"(pid {module_pid} zyje: {pid_alive(module_pid)})")
        check("J4c plugin zatrzymany", not pid_alive(plugin_pid))
        rd = run_dir()
        hub_log = (rd / "hub.log").read_text(encoding="utf-8", errors="replace")
        check("J4d w logu: modul zamknal sie sam po prosbie HUB-a", "zamknęła się sama" in hub_log)
        out4 = rd / f"modul-{MODULE}.wyjscie.log"
        check("J4e wyjscie.log w J4: bez tracebackow i wierszy w formacie logu", out4.exists() and wyjscie_ok(out4),
              f"({wyjscie_summary(out4)})")
        timer_log = (rd / "timer-plugin.log").read_text(encoding="utf-8", errors="replace") if (rd / "timer-plugin.log").exists() else ""
        check("J4f timer-plugin nie dostal recording_command (adresat tylko recorder/obs)", "recording_command" not in timer_log)
    finally:
        say("\n== J5. Sprzatanie")
        for pr in (hub,):
            if pr is not None and pr.poll() is None:
                subprocess.run(["taskkill", "/F", "/PID", str(pr.pid)], capture_output=True)
        for pid in set(spawned):
            if pid and pid_alive(pid):
                kill_pid_tree(pid)
        time.sleep(1)
        left = [p for p in set(spawned) if p and pid_alive(p)]
        stray = procs_under_dry()                      # procesy z folderu proby, ktorych nie sledzilismy (np. sieroty po zabitym HUB-ie)
        for pid in stray:
            kill_pid_tree(pid)
        left += stray
        results["J5 nic nie zostalo"] = not left and not port_busy(HUB_PORT) and not port_busy(MOD_PORT)
        say(f"J5 nic nie zostalo: {'ZALICZONY' if results['J5 nic nie zostalo'] else 'NIEZALICZONY'} "
            f"(zywe: {left}, port huba zajety: {port_busy(HUB_PORT)}, port modulu zajety: {port_busy(MOD_PORT)})")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        failed = [k for k, v in results.items() if not v]
        say(f"\nWYNIK: {'WSZYSTKO ZALICZONE' if not failed else 'NIEZALICZONE: ' + ', '.join(failed)}")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print(f"(wynik zapisany w {OUT})")


DB = None
if __name__ == "__main__":
    main()
