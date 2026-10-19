"""Proba nadzoru HUB-a przez manager (E2d3c2, scenariusze M5-M6) z prawdziwym HUB-em. Nadzor bez okna (python -m manager.supervisor),
ta sama logika co w broadcast_manager.py.

    modules\\.venv\\Scripts\\python.exe tests\\modules\\dry_run_nadzor.py [futsal_nalf]

Folder, porty (HUB 18100, modul 18101, kanal 18102, atrapa OBS 18104) i budowanie jak w dry_run_manager.py.
  M5. Nadzor uruchamia HUB (--module none), modul startuje kanalem; nadzor sie konczy ("zamkniecie okna"): HUB i modul dzialaja dalej;
      drugi nadzor tylko sie podlacza (ten sam HUB, bez drugiego startu).
  M6. HUB zabity silowo: nadzor uruchamia go ponownie, nowy HUB przejmuje modul (ten sam proces); trzy awarie = trzy restarty, czwarta = koniec
      (limit); po celowym POST /hub/stop przy zamknietej sesji: bez restartu, znacznik w pliku, kolejny nadzor tez nie uruchamia HUB-a.
  M9. Sprzatanie: nic z proby nie zostaje.
"""
import json, os, pathlib, signal, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dry_run_manager as d  # noqa: E402  (wspolne: folder, porty, budowanie, kanal, sprzatanie)

OUT = d.REPO / "wp-local" / "tests-out" / "dry_run_nadzor.txt"
MARKER = d.DRY / "manager-hub-zatrzymany.json"


def supervisor(tag, seconds, interval=0.5):
    out = open(d.DRY / f"nadzor-{tag}.txt", "w", encoding="utf-8")
    env = {**d.module_env(), "PYTHONPATH": str(d.REPO)}
    pr = subprocess.Popen([sys.executable, "-m", "manager.supervisor", "--config", str(d.DRY / "hub.json"), "--hub-exe", str(d.DRY / "hub.exe"),
                           "--run-seconds", str(seconds), "--interval", str(interval)], cwd=d.REPO, env=env, stdout=out, stderr=subprocess.STDOUT)
    d.spawned.append(pr.pid)
    return pr


def sup_log(tag):
    return (d.DRY / f"nadzor-{tag}.txt").read_text(encoding="utf-8", errors="replace")


def hub_pid():
    try:
        return d.state()["hub"]["pid"]
    except Exception:
        return None


def remember_hub():
    pid = hub_pid()
    if pid:
        d.spawned.append(pid)
    d.remember_pids()
    return pid


def main():
    for p in d.PORTS:
        if d.port_busy(p):
            sys.exit(f"Port {p} jest zajety. Niczego nie zabijam; sprawdz recznie.")
    r = subprocess.run([sys.executable, str(d.REPO / "tests" / "modules" / "prepare_dry_run.py"), d.MODULE], capture_output=True, text=True)
    if r.returncode:
        sys.exit("Przygotowanie bazy nie powiodlo sie:\n" + r.stdout[-1500:] + r.stderr[-1500:])
    d.DB = d.REPO / "modules" / d.MODULE / "instance" / "database-proba.db"
    import shutil
    shutil.rmtree(d.LOGS, ignore_errors=True)
    for f in ("uslugi.json", "manager-hub-zatrzymany.json", "manager-hub.json"):
        (d.DRY / f).unlink(missing_ok=True)
    d.build()
    sups = []
    try:
        d.say("== M5. Nadzor uruchamia HUB; zamkniecie nadzoru niczego nie zatrzymuje; drugi nadzor sie podlacza")
        s1 = supervisor("1", 60)
        sups.append(s1)
        up = d.wait_for(lambda: d.state()["protocol"] == 1, 40)
        d.check("M5a nadzor uruchomil HUB (kanal odpowiada)", up and "uruchamiam hub.exe --module none" in sup_log("1"), f"({sup_log('1')[-300:]!r})")
        h1 = remember_hub()
        code, res = d.ctl("POST", "/module/start", {"id": "proba"})
        running = code == 202 and d.wait_for(lambda: (d.active() or {}).get("state") == "running", 120)
        mod_pid = (d.active() or {}).get("pid")
        d.check("M5b modul uruchomiony kanalem", running, f"({code} {res} {d.active()})")
        d.remember_pids()
        d.wait_for(lambda: d.state()["session"]["known"], 30)
        s1.terminate()                                   # jak zamkniecie okna managera (nadzor znika bez sprzatania)
        s1.wait(10)
        time.sleep(3)
        alive = d.pid_alive(h1) and mod_pid and d.pid_alive(mod_pid) and (d.active() or {}).get("pid") == mod_pid
        d.check("M5c po zamknieciu nadzoru HUB i modul dzialaja dalej", alive, f"(HUB {h1}, modul {mod_pid}, active={d.active()})")
        s2 = supervisor("2", 8)
        sups.append(s2)
        s2.wait(30)
        log2 = sup_log("2")
        d.check("M5d drugi nadzor tylko sie podlacza (ten sam HUB, bez startu)", "podłączono do HUB-a" in log2 and "uruchamiam" not in log2
                and hub_pid() == h1, f"({log2!r})")

        d.say("\n== M6. Awaria HUB-a: restart (najwyzej 3 z rzedu), przejecie modulu; celowe zatrzymanie bez restartu")
        s3 = supervisor("3", 400)
        sups.append(s3)
        d.wait_for(lambda: "podłączono do HUB-a" in sup_log("3"), 20)
        prev = h1
        for i in range(1, 4):
            subprocess.run(["taskkill", "/F", "/PID", str(prev)], capture_output=True)
            back = d.wait_for(lambda: hub_pid() not in (None, prev), 60)
            new = remember_hub()
            same_mod = d.wait_for(lambda: (d.active() or {}).get("pid") == mod_pid, 30)
            d.check(f"M6a{i} HUB zabity: restart {i} z 3, nowy HUB przejal ten sam modul", back and same_mod and f"restart {i} z 3" in sup_log("3"),
                    f"(HUB {prev} -> {new}, active={d.active()})")
            prev = new
        subprocess.run(["taskkill", "/F", "/PID", str(prev)], capture_output=True)
        gave_up = d.wait_for(lambda: "limit 3 restartów wyczerpany" in sup_log("3"), 30)
        time.sleep(5)
        d.check("M6b czwarta awaria: nadzor przestaje (limit), HUB nie wraca", gave_up and hub_pid() is None, f"({sup_log('3')[-400:]!r})")
        s3.terminate()
        s3.wait(10)
        d.check("M6c modul przezyl awarie HUB-a", d.pid_alive(mod_pid))
        s4 = supervisor("4", 120)
        sups.append(s4)
        up = d.wait_for(lambda: hub_pid() is not None and (d.active() or {}).get("pid") == mod_pid, 60)
        h4 = remember_hub()
        d.check("M6d nowy nadzor uruchamia HUB, ktory przejmuje modul", up, f"(HUB {h4}, active={d.active()})")
        d.wait_for(lambda: d.state()["session"]["known"] and d.session_state() == "none", 30)
        code, res = d.ctl("POST", "/hub/stop", {})
        d.check("M6e POST /hub/stop przyjety przy zamknietej sesji", code == 202, f"({code} {res})")
        # nadzor sam nie wysyla /hub/stop (to robi okno); znacznik zapisuje okno po przyjeciu polecenia: tu jak okno
        MARKER.write_text(json.dumps({"pid": h4, "at": "proba"}), encoding="utf-8")
        gone = d.wait_for(lambda: not d.pid_alive(h4), 60)
        time.sleep(6)
        log4 = sup_log("4")
        d.check("M6f po celowym zatrzymaniu: HUB zakonczony, bez restartu", gone and hub_pid() is None and "bez restartu" in log4
                and log4.count("restart ") == 0, f"({log4[-400:]!r})")
        s4.terminate()
        s4.wait(10)
        s5 = supervisor("5", 6)
        sups.append(s5)
        s5.wait(30)
        log5 = sup_log("5")
        d.check("M6g kolejny nadzor respektuje znacznik w pliku (nie uruchamia HUB-a)", "uruchamiam" not in log5 and "stopped" in log5
                and hub_pid() is None, f"({log5!r})")
    finally:
        d.say("\n== M9. Sprzatanie")
        for s in sups:
            if s.poll() is None:
                s.terminate()
        pid = hub_pid()
        if pid:
            d.spawned.append(pid)
            try:
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            except OSError:
                pass
            d.wait_for(lambda: not d.pid_alive(pid), 60)
        for p in set(d.spawned):
            if p and d.pid_alive(p):
                d.kill_tree(p)
        stray = d.procs_under_dry()
        for p in stray:
            d.kill_tree(p)
        for port in d.PORTS:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  f"Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ $_.OwningProcess }}"],
                                 capture_output=True, text=True).stdout
            for x in out.split():
                if x.isdigit():
                    d.kill_tree(int(x))
                    stray.append(int(x))
        time.sleep(1)
        left = [p for p in set(d.spawned) if p and d.pid_alive(p)] + stray
        d.check("M9 nic nie zostalo", not left and not any(d.port_busy(p) for p in d.PORTS),
                f"(zywe: {left}; zajete porty: {[p for p in d.PORTS if d.port_busy(p)]})")
        failed = [k for k, v in d.results.items() if not v]
        d.say(f"\nWYNIK: {'WSZYSTKO ZALICZONE' if not failed else 'NIEZALICZONE: ' + ', '.join(failed)}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(d.lines), encoding="utf-8")
        print(f"(wynik zapisany w {OUT})")


if __name__ == "__main__":
    main()
