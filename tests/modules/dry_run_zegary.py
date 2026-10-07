"""Proba z prawdziwym HUB-em i timer-pluginem (E1, krok 5): zegary wyliczane z okresu i GameTimer.

    modules\\.venv\\Scripts\\python.exe tests\\modules\\dry_run_zegary.py [futsal_nalf]

Buduje swiezo hub i timer-plugin z kodu zrodlowego do wp-local/dryrun/ (nie rusza plikow .exe w repo), przygotowuje baze
testowa (kopia lokalnej bazy modulu), uruchamia HUB (port 8080), timer-plugin (startowany przez HUB na deklaracje modulu)
i modul (port 8081) i przeprowadza scenariusze:
  A. start okresu 1 i zegara, B. przerwa i start okresu 2 (plugin ma dokladnie jeden zegar glowny),
  C. zabicie timer-pluginu w trakcie BIEGNACEGO okresu, D. zabicie timer-pluginu w trakcie PAUZY.
C i D tylko obserwuja: odtwarzanie zegara robione jest tak jak w timer-recovery.js; zapisujemy, co pokazuje zegar po odtworzeniu.
Wymaga wolnych portow 8080 i 8081 oraz braku uruchomionych hub.exe / timer-plugin.exe (wersja transmisyjna musi byc wylaczona).
"""
import json, os, pathlib, shutil, socket, sqlite3, subprocess, sys, threading, time, urllib.request

import socketio as sio_lib

REPO = pathlib.Path(__file__).resolve().parents[2]
MODULE = sys.argv[1] if len(sys.argv) > 1 else "futsal_nalf"
DRY = REPO / "wp-local" / "dryrun"
LOGS = DRY / "logs"
OUT = REPO / "wp-local" / "tests-out" / "dry_run_zegary.txt"
BASE = "http://127.0.0.1:8081"
lines = []


def say(msg=""):
    print(msg, flush=True)
    lines.append(msg)


def port_busy(p):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", p)) == 0


def running(image):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}"], capture_output=True, text=True).stdout
    return image.lower() in out.lower()


def http(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
        try:
            return json.loads(raw)
        except ValueError:
            return raw


class Panel:
    """Klient socket.io udajacy panel operatora."""
    def __init__(self):
        self.c = sio_lib.Client()
        self.ev = threading.Event()
        self.last = None
        self.c.on("timer_plugin_all_timers", self._on_all)
        self.c.connect(BASE)

    def _on_all(self, data):
        self.last = data
        self.ev.set()

    def timers(self, timeout=6):
        self.ev.clear()
        self.c.emit("timer_plugin_request_all_timers")
        if not self.ev.wait(timeout):
            return None
        return (self.last or {}).get("timers", [])

    def emit(self, name, data=None):
        self.c.emit(name, data or {})


def elapsed_of(timers, timer_id):
    """(czas WYSWIETLANY = initial_time + elapsed_time, stan). W pluginie initial_time to przesuniecie dodawane do wyswietlanego
    czasu, a elapsed_time liczy od zera (timer.go: 'always added to display')."""
    for t in timers or []:
        if t.get("timer_id") == timer_id:
            return (t.get("initial_time") or 0) + (t.get("elapsed_time") or 0), t.get("state")
    return None, None


def main_ids(timers, all_main_names):
    return sorted(t["timer_id"] for t in (timers or []) if t.get("timer_id") in all_main_names)


def ui_recovery(panel, label):
    """Odtwarzanie jak w timer-recovery.js: brak zegara w pluginie -> utworz z initial_time = elapsed (albo initial_time), start jesli 'running'."""
    st = http("GET", "/api/settings")
    main = (st.get("current_timers") or {}).get("main")
    timers = panel.timers()
    ids = {t.get("timer_id") for t in timers or []}
    info = {"settings_main": main, "plugin_timers_before_recovery": sorted(ids)}
    if main and main["timer_id"] not in ids:
        payload = {"timer_id": main["timer_id"], "timer_type": main.get("timer_type", "independent"),
                   "initial_time": main.get("elapsed_time") or main.get("initial_time") or 0, "limit": main["limit"],
                   "pause_at_limit": main.get("pause_at_limit") is not False, "metadata": main.get("metadata") or {}}
        panel.emit("timer_plugin_create_timer", payload)
        if main["state"] == "running":
            time.sleep(0.1)
            panel.emit("timer_plugin_start_timer", {"timer_id": main["timer_id"]})
        info["created_with_initial_time"] = payload["initial_time"]
    return info


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
    cfg = {"timer-plugin": {
        "id": "timer-plugin", "name": "Timer Plugin", "type": "local",
        "executable_path": str(DRY / "timer-plugin.exe"), "working_dir": str(DRY / "timer-plugin"), "args": [],
        "env": ["PLUGIN_ID=timer-plugin", "HUB_URL=ws://localhost:8080/ws"],
        "auto_start": True, "restart_on_crash": True, "max_restarts": 10, "restart_delay_ms": 3000, "startup_delay_ms": 1000,
        "health_check_interval": 10, "is_critical": False}}
    (DRY / "hub" / "config" / "plugins.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (DRY / "hub" / "config" / "overlays.json").write_text("[]", encoding="utf-8")


def main():
    for p in (8080, 8081):
        if port_busy(p):
            sys.exit(f"Port {p} jest zajety. Zamknij wersje transmisyjna i sprobuj ponownie.")
    for image in ("hub.exe", "timer-plugin.exe", "broadcast-hub.exe"):
        if running(image):
            sys.exit(f"Dziala {image} (wersja transmisyjna?). Zamknij ja i sprobuj ponownie; niczego nie zabijam.")
    py = sys.executable
    r = subprocess.run([py, str(REPO / "tests" / "modules" / "prepare_dry_run.py"), MODULE], capture_output=True, text=True)
    if r.returncode:
        sys.exit("Przygotowanie bazy nie powiodlo sie:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    db_path = REPO / "modules" / MODULE / "instance" / "database-proba.db"
    build()
    procs = []
    try:
        hub = subprocess.Popen([str(DRY / "hub.exe")], cwd=DRY / "hub", stdout=open(LOGS / "hub.log", "w"), stderr=subprocess.STDOUT)
        procs.append(hub)
        for _ in range(40):
            if port_busy(8080):
                break
            time.sleep(0.25)
        env = {**os.environ, "DATABASE_URL": "sqlite:///" + db_path.as_posix(), "BM_REQUIRED_PLUGINS": "timer-plugin", "PYTHONIOENCODING": "utf-8"}
        mod = subprocess.Popen([py, str(REPO / "tests" / "modules" / "dry_run_module.py"), MODULE], env=env,
                               stdout=open(LOGS / "modul.log", "w"), stderr=subprocess.STDOUT)
        procs.append(mod)
        for _ in range(120):
            try:
                http("GET", "/api/session")
                break
            except Exception:
                time.sleep(0.5)
        else:
            sys.exit("Modul nie wystartowal (patrz wp-local/dryrun/logs/modul.log)")
        panel = Panel()
        for _ in range(60):                               # czekamy az HUB uruchomi timer-plugin
            if panel.timers(timeout=2) is not None:
                break
            time.sleep(1)
        else:
            sys.exit("Timer-plugin nie odpowiada (patrz logi)")
        scenarios(panel, db_path)
    finally:
        for pr in procs:
            pr.terminate()
        subprocess.run(["taskkill", "/F", "/IM", "timer-plugin.exe"], capture_output=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")


def scenarios(panel, db_path):
    con = sqlite3.connect(db_path)
    gid = con.execute("select id from games where status = 0 and id not in (select game_id from periods) order by id limit 1").fetchone()[0]
    con.close()
    say(f"Mecz testowy: game_id={gid} (baza {db_path.name})")
    http("GET", f"/games/{gid}/prepare-broadcast")
    http("GET", f"/games/{gid}/select-broadcast")
    con = sqlite3.connect(db_path)
    periods = con.execute("select id, main_timer_name, status from periods where game_id=? order by period_order", (gid,)).fetchall()
    con.close()
    (p1, n1, _), (p2, n2, _) = periods[0], periods[1]
    mains = {n1, n2}
    s = http("GET", "/api/session")
    say(f"Sesja po wyborze meczu: status={s['status']}, game_id={s['game_id']}, period_id={s['period_id']} (oczekiwano okres {p1})")

    say("\n== A. Start okresu 1 i zegara")
    http("POST", f"/api/period/{p1}/start")
    time.sleep(1)
    panel.emit("timer_start", {"timer_id": n1})
    time.sleep(3.5)
    t = panel.timers()
    st = http("GET", "/api/settings")["current_timers"]["main"]
    say(f"plugin: zegary glowne={main_ids(t, mains)}, {n1}: czas wyswietlany/stan={elapsed_of(t, n1)}")
    say(f"panel (current_timers): {st['timer_id']} stan={st['state']} elapsed={st['elapsed_time']}")

    say("\n== B. Pauza, koniec okresu 1, przerwa, start okresu 2")
    panel.emit("timer_pause", {"timer_id": n1})
    time.sleep(1)
    http("POST", f"/api/period/{p1}/finish")
    time.sleep(1)
    d = http("GET", "/api/settings")
    say(f"przerwa: current_period_id={d['current_period_id']} (oczekiwano {p1}), status okresu={d['period']['status']} (2 = zakonczony), "
        f"zegar w panelu={d['current_timers']['main']['timer_id']} stan={d['current_timers']['main']['state']}")
    http("POST", f"/api/period/{p2}/start")
    time.sleep(1.5)
    t = panel.timers()
    ids = main_ids(t, mains)
    say(f"po starcie okresu 2: zegary glowne w pluginie={ids}  -> {'OK: dokladnie jeden (okres 2)' if ids == [n2] else 'UWAGA: oczekiwano tylko ' + n2}")
    panel.emit("timer_start", {"timer_id": n2})
    time.sleep(3)

    say("\n== C. Zabicie timer-pluginu w trakcie BIEGNACEGO okresu 2")
    t = panel.timers()
    say(f"(wpis zegara w pluginie: { [x for x in t if x.get('timer_id') == n2] })")
    before_display, bstate = elapsed_of(t, n2)
    before_db = http("GET", "/api/settings")["current_timers"]["main"]
    say(f"przed zabiciem: plugin pokazuje={before_display} stan={bstate}; panel elapsed={before_db['elapsed_time']} stan={before_db['state']}")
    kill_and_recover(panel, n2, before_display, bstate, "C")

    say("\n== D. Zabicie timer-pluginu w trakcie PAUZY okresu 2")
    panel.emit("timer_pause", {"timer_id": n2})
    time.sleep(2)
    t = panel.timers()
    before_display, bstate = elapsed_of(t, n2)
    before_db = http("GET", "/api/settings")["current_timers"]["main"]
    say(f"przed zabiciem: plugin pokazuje={before_display} stan={bstate}; panel elapsed={before_db['elapsed_time']} stan={before_db['state']}")
    kill_and_recover(panel, n2, before_display, bstate, "D")


def kill_and_recover(panel, timer_id, before_display, before_state, label):
    """Zabija timer-plugin, czeka na ponowne uruchomienie przez HUB, odtwarza zegar jak timer-recovery.js i zapisuje, co pokazuje zegar.

    Porownanie: 'powinien pokazywac' = czas przed zabiciem + czas, ktory uplynal od zabicia (dla biegnacego) albo sam czas
    przed zabiciem (dla spauzowanego). 'Cofniecie' = powinien - pokazuje."""
    t_kill = time.time()
    subprocess.run(["taskkill", "/F", "/IM", "timer-plugin.exe"], capture_output=True)
    up = None
    for _ in range(60):
        time.sleep(1)
        tm = panel.timers(timeout=2)
        if tm is not None:
            up = time.time() - t_kill
            break
    if up is None:
        say("timer-plugin nie wrocil w 60 s")
        return
    say(f"timer-plugin wrocil po ok. {up:.0f} s od zabicia (HUB uruchomil go ponownie)")
    info = ui_recovery(panel, label)
    say(f"zegary w pluginie zaraz po restarcie: {info['plugin_timers_before_recovery']}")
    sm = info["settings_main"] or {}
    say(f"panel pokazuje (dane do odtworzenia): stan={sm.get('state')} elapsed={sm.get('elapsed_time')}")
    if "created_with_initial_time" in info:
        say(f"odtworzenie jak w timer-recovery.js: utworzono zegar z initial_time={info['created_with_initial_time']}"
            + (" i uruchomiono" if sm.get("state") == "running" else " (bez uruchamiania: stan nie byl 'running')"))
    else:
        say("zegar byl juz w pluginie, odtwarzanie niepotrzebne")
    time.sleep(1.5)
    shown, astate = elapsed_of(panel.timers(), timer_id)
    t_m = time.time()
    should = before_display + ((t_m - t_kill) * 1000 if before_state == "running" else 0)
    lag = should - shown if shown is not None else None
    say(f"PRZED zabiciem: zegar pokazywal {before_display} ms, stan={before_state}")
    say(f"PO odtworzeniu: zegar pokazuje {shown} ms, stan={astate}")
    say(f"zegar powinien pokazywac ok. {should:.0f} ms; cofniecie wzgledem rzeczywistego czasu: {lag:.0f} ms (o {lag/1000:.1f} s)"
        if lag is not None else "brak danych")
    say(f"wzgledem wartosci sprzed zabicia: {shown - before_display:+.0f} ms")


if __name__ == "__main__":
    main()
