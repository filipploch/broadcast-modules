"""W7d, kroki 3-4: próba z prawdziwym HUB-em i prawdziwym modułem na KOPII bazy roboczej z pobranymi danymi (bez OBS).

    modules\\.venv\\Scripts\\python.exe tests\\modules\\dry_run_w7d.py <futsal_nalf|garbarnia> [--krotka]

Wymaga: wolnych portów 18080/18081, działającej instancji WP TEGO modułu (do ponownego pobrania na kopii), baz roboczych z danymi po W7d.
Nie dotyka bazy roboczej (kopia: modules/<moduł>/instance/database-proba.db, robi ją prepare_dry_run.py), folderu transmisyjnego ani OBS.
  W1. Kopia bazy + test dymny wszystkich tras GET na danych z WP.
  W2. HUB uruchamia prawdziwy moduł na kopii; moduł łączy się z HUB-em; timer-plugin wstaje.
  W3. Adresy logo po HTTP dla WSZYSTKICH drużyn (200 i obraz); dane meczów po HTTP (/api/games/<id>) dla WSZYSTKICH meczów zgodne z bazą:
      nazwa 14-znakowa, skrót, logo, nazwa rundy (nakładki biorą te pola).
  W4. Mecz z pobranych danych: przygotowanie (okresy), wybór do transmisji, sesja otwarta z tym meczem, HUB zna stan sesji.
  W5. Ponowne pobranie z WP przy aktywnym meczu: mecz pominięty (wynik "z modułu" nie zostaje nadpisany), reszta bez zmian.
  W6. (bez --krotka) 3 minuty bez restartów modułu i pluginu.
  W7. Sprzątanie: nic nie zostaje."""
import json
import pathlib
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(encoding='utf-8')
_args = [a for a in sys.argv[1:] if not a.startswith('--')]
_module = _args[0] if _args else 'futsal_nalf'
sys.argv = [sys.argv[0], _module] + [a for a in sys.argv[1:] if a.startswith('--')]
import dry_run_hub_modul as H  # noqa: E402  (stałe i narzędzia próby z HUB-em; moduł z argv)

REPO, MODULE, MOD, SHORT = H.REPO, H.MODULE, H.MOD, H.SHORT
OUT = REPO / 'wp-local' / 'tests-out' / f'dry_run_w7d_{MODULE}.txt'
PY = sys.executable


def http(url, timeout=20):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.headers.get('Content-Type', ''), r.read()
    except urllib.error.HTTPError as e:
        return e.code, '', b''


def jget(path):
    s, _, body = http(MOD + path)
    return json.loads(body.decode('utf-8')) if s == 200 and body else None


def main():
    for p in (H.HUB_PORT, H.MOD_PORT):
        if H.port_busy(p):
            sys.exit(f'Port {p} jest zajęty. Niczego nie zabijam; sprawdź ręcznie.')
    H.say(f'== W1. Kopia bazy roboczej ({MODULE}) i test dymny tras GET')
    r = subprocess.run([PY, str(HERE / 'prepare_dry_run.py'), MODULE], capture_output=True, text=True)
    H.check('W1a prepare_dry_run (migracja kopii + test dymny tras GET na danych z WP)', r.returncode == 0, r.stdout[-300:].replace('\n', ' | ') + r.stderr[-200:])
    if r.returncode:
        return
    H.DB = REPO / 'modules' / MODULE / 'instance' / 'database-proba.db'
    db = sqlite3.connect(H.DB.as_posix())
    n_gier = db.execute('select count(*) from games').fetchone()[0]
    H.check('W1b kopia ma dane z WP (a nie dane próbne)', db.execute("select count(*) from game_foreign_ids").fetchone()[0] == n_gier and n_gier > 50, f'(mecze: {n_gier})')
    import shutil
    shutil.rmtree(H.DRY / 'logs', ignore_errors=True)
    shutil.rmtree(H.DRY / 'timer-plugin' / 'state', ignore_errors=True)
    H.build()
    hub = None
    try:
        H.say('\n== W2. HUB uruchamia prawdziwy moduł na kopii')
        hub = H.start_hub('w7d')
        ready = H.wait_for(lambda: H.status()['services']['module']['status'] == 'online', 150)
        if not H.check('W2a moduł uruchomiony przez HUB i gotowy', ready):
            return
        mod_pid = H.status()['services']['module']['pid']
        H.spawned.append(mod_pid)
        H.check('W2b moduł połączony z HUB-em', H.wait_for(lambda: H.status()['main_module_connected'], 30))
        got = H.wait_for(lambda: 'timer-plugin' in H.status()['connected_plugins'], 60)
        H.check('W2c HUB uruchomił timer-plugin', got)
        if got:
            H.spawned.append(H.status()['plugin_manager']['local_plugins']['timer-plugin']['pid'])

        H.say('\n== W3. Logo i dane meczów po HTTP, wszystkie pobrane drużyny i mecze')
        teams = db.execute('select id, name, name_14, short_name, logo_path from teams').fetchall()
        zle_logo = []
        for tid, nm, n14, sh, logo in teams:
            s, ct, body = http(f'{MOD}/{logo.lstrip("/")}')
            if not (s == 200 and ct.startswith('image/') and len(body) > 100):
                zle_logo.append((nm, logo, s, ct))
        H.check(f'W3a adresy logo wszystkich drużyn zwracają obraz ({len(teams)} drużyn)', not zle_logo, zle_logo[:5])
        games = db.execute('select g.id, h.name_14, h.short_name, h.logo_path, a.name_14, a.short_name, a.logo_path, l.name, g.round, g.status, g.home_team_goals, g.away_team_goals '
                           'from games g join teams h on h.id=g.home_team_id join teams a on a.id=g.away_team_id join leagues l on l.id=g.league_id').fetchall()
        zle = []
        for gid, hn14, hsh, hlogo, an14, ash, alogo, liga, rnd, st, hg, ag in games:
            d = jget(f'/api/games/{gid}')
            ok = (d and d['home_team_name_14'] == hn14 and d['away_team_name_14'] == an14 and d['home_team_short_name'] == hsh and d['away_team_short_name'] == ash
                  and d['home_team_logo'] == hlogo and d['away_team_logo'] == alogo and d['league_name'] == liga and d['round'] == rnd
                  and len(d['home_team_name_14']) <= 14 and len(d['away_team_name_14']) <= 14 and d['home_team_goals'] == hg and d['away_team_goals'] == ag
                  and ((d['round_name'] == '') == (rnd == 0)))
            if not ok:
                zle.append(gid)
        H.check(f'W3b dane meczów po HTTP zgodne z bazą i kompletne dla nakładek ({len(games)} meczów)', not zle, zle[:5])
        puchar = [g for g in games if 'puchar' in g[7].lower()]
        if puchar:
            names = {jget(f'/api/games/{g[0]}')['round_name'] for g in puchar}
            H.check('W3c nazwy rund Pucharu poprawne (bez wyjątku)', all(any(k in n for k in ('finału', 'Ćwierćfinał', 'Półfinał', 'Finał', 'Mecz o')) for n in names), sorted(names))

        H.say('\n== W4. Mecz z pobranych danych: przygotowanie, wybór do transmisji, sesja')
        g = db.execute("select g.id from games g where g.status=0 order by g.date limit 1").fetchone()[0]
        s1, _, _ = http(f'{MOD}/games/{g}/prepare-broadcast')           # przekierowanie podąża samo
        okresy = jget(f'/api/games/{g}')['periods']
        H.check('W4a przygotowanie meczu do transmisji tworzy okresy', s1 == 200 and len(okresy) >= 2, f'(okresów {len(okresy)})')
        s2, _, _ = http(f'{MOD}/games/{g}/select-broadcast')
        ses = jget('/api/session')
        H.check('W4b wybór meczu otwiera sesję z tym meczem', s2 == 200 and ses and ses.get('open') and str(g) in json.dumps(ses), f'(sesja: {json.dumps(ses, ensure_ascii=False)[:160]})')
        sess_hub = H.wait_for(lambda: H.status()['session']['known'] is True and H.status()['session']['state'] != 'none', 30)
        H.check('W4c HUB zna stan sesji po wyborze meczu', sess_hub, f'({H.status().get("session")})')

        H.say('\n== W5. Ponowne pobranie z WP przy aktywnym meczu: mecz pominięty')
        db.execute('update games set home_team_goals=3, away_team_goals=1 where id=?', (g,))      # jakby w module trwały zmiany; WP: mecz nierozpoczęty
        db.commit()
        liga = db.execute('select l.name from games g join leagues l on l.id=g.league_id where g.id=?', (g,)).fetchone()[0]
        frag = 'puchar' if 'puchar' in liga.lower() else liga.lower()
        pr = subprocess.run([PY, str(HERE / 'pobranie_na_kopii_w7d.py'), MODULE, H.DB.as_posix(), frag, '1'], capture_output=True, text=True)
        try:
            w = json.loads(pr.stdout.strip().splitlines()[-1])
        except Exception:
            w = {'ok': False, 'blad': (pr.stdout + pr.stderr)[-300:]}
        wynik = db.execute('select home_team_goals, away_team_goals from games where id=?', (g,)).fetchone()
        H.check('W5a mecz aktywny w sesji pominięty, jego wynik z modułu nie został nadpisany', w.get('ok') and wynik == (3, 1) and any('sesji' in x for x in (w.get('pominiete') or [])),
                f'(wynik w bazie {wynik}; pominięte: {(w.get("pominiete") or [])[:1]}; błąd: {w.get("blad")})')
        H.check('W5b reszta bez zmian (0 dodanych i zaktualizowanych)', w.get('ok') and all(v['dodano'] == 0 and v['zaktualizowano'] == 0 for v in (w.get('liczniki') or {}).values()), json.dumps(w.get('liczniki')))

        if not SHORT:
            H.say('\n== W6. Stabilność: 3 minuty bez restartów')
            end = time.time() + 420
            while time.time() < end:
                st = H.status()
                if st['services']['module'].get('uptime_s', 0) >= 180 and min(p.get('uptime_s', 0) for p in st['plugin_manager']['local_plugins'].values()) >= 180:
                    break
                time.sleep(5)
            st = H.status()
            mod = st['services']['module']
            local = st['plugin_manager']['local_plugins']
            rd = H.run_dir()
            timeouts = (rd / 'hub.log').read_text(encoding='utf-8', errors='replace').count('heartbeat timeout')
            H.check('W6 3 minuty bez restartów (moduł i pluginy)', mod['status'] == 'online' and mod['restarts'] == 0 and mod.get('uptime_s', 0) >= 180
                    and all(p['status'] == 'online' and p['restarts'] == 0 for p in local.values()) and timeouts == 0,
                    f"(moduł {mod['status']} restarts={mod['restarts']} uptime={mod.get('uptime_s')} s; timeouty heartbeatu: {timeouts})")
        else:
            H.say('W6 POMINIĘTY (--krotka)')
        rd = H.run_dir()
        out_file = rd / f'modul-{MODULE}.wyjscie.log'
        H.check('W6b wyjscie.log modułu: bez tracebacków', out_file.exists() and H.wyjscie_ok(out_file), H.wyjscie_summary(out_file) if out_file.exists() else 'brak pliku')
    finally:
        H.say('\n== W7. Sprzątanie')
        if hub is not None and hub.poll() is None:
            subprocess.run(['taskkill', '/F', '/PID', str(hub.pid)], capture_output=True)
        for pid in set(H.spawned):
            if pid and H.pid_alive(pid):
                H.kill_pid_tree(pid)
        time.sleep(1)
        left = [p for p in set(H.spawned) if p and H.pid_alive(p)]
        stray = H.procs_under_dry()
        for pid in stray:
            H.kill_pid_tree(pid)
        left += stray
        ok = not left and not H.port_busy(H.HUB_PORT) and not H.port_busy(H.MOD_PORT)
        H.results['W7 nic nie zostało'] = ok
        H.say(f'W7 nic nie zostało: {"ZALICZONY" if ok else "NIEZALICZONY"} (żywe: {left}, port huba zajęty: {H.port_busy(H.HUB_PORT)}, port modułu zajęty: {H.port_busy(H.MOD_PORT)})')
        OUT.parent.mkdir(parents=True, exist_ok=True)
        failed = [k for k, v in H.results.items() if not v]
        H.say(f'\nWYNIK ({MODULE}): {"WSZYSTKO ZALICZONE" if not failed else "NIEZALICZONE: " + ", ".join(failed)}')
        OUT.write_text('\n'.join(H.lines), encoding='utf-8')
        print(f'(wynik zapisany w {OUT})')
        sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
