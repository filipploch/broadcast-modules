"""T6: dwie bazy rozgrywek na jednym kodzie WordPressa (wybor bazy po porcie), SQLite, zakladanie nowej bazy z szablonu.

    python tests/wp/t6.py
Wymaga: wp-config.php dolaczajacego wp-plugin/multidb/bm-multidb.php oraz tests-out/t1_scen.json (python tests/wp/run_t1.py).
Nie dotyka serwera na 8090 ani jego bazy (tylko odczyt kopii).
Baza 8091 = "Futsal NALF" (kryteria t1-nalf), baza 8092 = "IV liga MZPN" (kryteria t1-mzpn).
"""
import json, os, shutil, socket, sqlite3, subprocess, sys, time, urllib.request
import common
from common import OUT, WP_LOCAL, PHP, WP_PATH, api, install_test_plugin

DBS = WP_LOCAL / "databases"
SRC = WP_PATH / "wp-content" / "database" / ".ht.sqlite"
PORTS = {8091: ("Futsal NALF (test T6)", "t1-nalf", "NALF"), 8092: ("IV liga MZPN (test T6)", "t1-mzpn", "MZPN")}
ok_all = True


def check(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(f"  [{'OK' if cond else 'BLAD'}] {name} {detail}", flush=True)


def wp_db(env_extra, *args):
    r = subprocess.run([str(PHP), str(common.WPCLI), f"--path={WP_PATH}", *args], capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, **env_extra})
    if r.returncode:
        raise RuntimeError(r.stderr or r.stdout)
    return r.stdout.strip()


def port_free(p):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", p)) != 0


def make_template():
    """Szablon = kopia bazy testowej bez danych rozgrywek (zostaje konfiguracja SportsPress, kolumny, kryteria H2H, uzytkownik)."""
    d = DBS / "_szablon"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    src = sqlite3.connect(f"file:{SRC.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(d / ".ht.sqlite")
    src.backup(dst)
    src.close()
    c = dst.cursor()
    types = ("sp_event", "sp_team", "sp_player", "sp_staff", "sp_table", "sp_list", "revision", "auto-draft")
    q = ",".join("?" * len(types))
    c.execute(f"DELETE FROM wp_postmeta WHERE post_id IN (SELECT ID FROM wp_posts WHERE post_type IN ({q}))", types)
    c.execute(f"DELETE FROM wp_term_relationships WHERE object_id IN (SELECT ID FROM wp_posts WHERE post_type IN ({q}))", types)
    c.execute(f"DELETE FROM wp_posts WHERE post_type IN ({q})", types)
    tx = "SELECT term_id FROM wp_term_taxonomy WHERE taxonomy IN ('sp_league','sp_season')"
    c.execute(f"DELETE FROM wp_termmeta WHERE term_id IN ({tx})")
    c.execute(f"DELETE FROM wp_terms WHERE term_id IN ({tx})")
    c.execute("DELETE FROM wp_term_taxonomy WHERE taxonomy IN ('sp_league','sp_season')")
    c.execute("DELETE FROM wp_term_relationships WHERE object_id NOT IN (SELECT ID FROM wp_posts)")
    dst.commit()
    dst.execute("VACUUM")
    dst.close()
    return d / ".ht.sqlite"


def new_db_from_template(port):
    t0 = time.time()
    d = DBS / f"p{port}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    shutil.copy(DBS / "_szablon" / ".ht.sqlite", d / ".ht.sqlite")
    wp_db({"BM_PORT": str(port)}, "option", "update", "blogname", PORTS[port][0])
    return time.time() - t0


def main():
    for p in PORTS:
        if not port_free(p):
            sys.exit(f"Port {p} jest zajety; zwolnij go i uruchom ponownie.")
    install_test_plugin()
    n_before = int(wp_db({}, "post", "list", "--post_type=sp_event", "--format=count"))
    print("1. Szablon bazy")
    tpl = make_template()
    c = sqlite3.connect(tpl)
    left = c.execute("SELECT count(*) FROM wp_posts WHERE post_type IN ('sp_event','sp_team','sp_player','sp_table')").fetchone()[0]
    cols = c.execute("SELECT count(*) FROM wp_posts WHERE post_type='sp_column'").fetchone()[0]
    c.close()
    check("szablon bez danych rozgrywek", left == 0, f"(meczow/druzyn/zawodnikow/tabel: {left}; kolumn SportsPress zostaje: {cols}; {tpl.stat().st_size/1e6:.1f} MB)")
    print("2. Zakladanie baz z szablonu")
    for p in PORTS:
        check(f"baza dla portu {p} zalozona z szablonu", True, f"({new_db_from_template(p):.1f} s)")
    print("3. Dwa serwery na jednym kodzie")
    procs = []
    try:
        for p in PORTS:
            procs.append(subprocess.Popen([str(PHP), "-S", f"127.0.0.1:{p}", "-t", str(WP_PATH)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(3)
        for p, (title, crit, rule) in PORTS.items():
            html = urllib.request.urlopen(f"http://127.0.0.1:{p}/wp-login.php", timeout=60).read().decode("utf-8", "ignore")
            check(f"port {p} odpowiada i ma wlasny adres", f"127.0.0.1:{p}" in html and f"127.0.0.1:{[q for q in PORTS if q != p][0]}" not in html, f"(baza: {title})")
        print("4. Niezalezne reguly tabel, te same mecze w obu bazach")
        scen = [s for s in json.load(open(OUT / "t1_scen.json")) if s["ref"]["NALF"]["order"] != s["ref"]["MZPN"]["order"]][:4]
        if len(scen) < 4:
            sys.exit("Brak scenariuszy NALF!=MZPN w tests-out/t1_scen.json: uruchom najpierw: python tests/wp/run_t1.py")
        got = {}
        for p, (title, crit, rule) in PORTS.items():
            base = f"http://127.0.0.1:{p}"
            for s in scen:
                lg = api("POST", "leagues", {"name": f"S{s['id']}"}, base=base)["id"]
                ss = api("POST", "seasons", {"name": f"S{s['id']}"}, base=base)["id"]
                tid = {t: api("POST", "teams", {"title": f"Z{t:02d}", "status": "publish", "leagues": [lg], "seasons": [ss]}, base=base)["id"] for t in s["teams"]}
                for i, (h, a, hg, ag) in enumerate(s["games"]):
                    oh = "win" if hg > ag else "draw" if hg == ag else "loss"
                    oa = {"win": "loss", "draw": "draw", "loss": "win"}[oh]
                    api("POST", "events", {"title": "m", "status": "publish", "date": f"2026-01-{1+i//10:02d}T{8+i%10:02d}:00:00", "format": "league",
                        "leagues": [lg], "seasons": [ss], "teams": [tid[h], tid[a]],
                        "results": {str(tid[h]): {"goals": str(hg), "outcome": [oh]}, str(tid[a]): {"goals": str(ag), "outcome": [oa]}}}, base=base)
                php = (f"$tb=wp_insert_post(['post_type'=>'sp_table','post_title'=>'t','post_status'=>'publish']);update_post_meta($tb,'sp_select','manual');"
                       f"foreach({json.dumps(list(tid.values()))} as $t) add_post_meta($tb,'sp_team',$t);wp_set_object_terms($tb,[{lg}],'sp_league');wp_set_object_terms($tb,[{ss}],'sp_season');"
                       f"update_post_meta($tb,'sah2h_criteria','{crit}');echo $tb;")
                tb = wp_db({"BM_PORT": str(p)}, "eval", php)
                r = api("GET", f"table/{tb}", ns="bm/v1", base=base)
                inv = {v: k for k, v in tid.items()}
                got[(p, s["id"])] = [inv[x["team"]] for x in r["virtual"]]
        for p, (title, crit, rule) in PORTS.items():
            okc = sum(got[(p, s["id"])] == s["ref"][rule]["order"] for s in scen)
            check(f"baza {p} ({rule}): kolejnosc zgodna z referencja {rule}", okc == len(scen), f"({okc}/{len(scen)})")
        diff = sum(got[(8091, s["id"])] != got[(8092, s["id"])] for s in scen)
        check("te same mecze, rozne reguly daja rozne tabele w roznych bazach", diff == len(scen), f"({diff}/{len(scen)})")
        print("5. Izolacja")
        for p in PORTS:
            n = len(api("GET", "events?per_page=100&_fields=id", base=f"http://127.0.0.1:{p}"))
            check(f"baza {p} ma tylko swoje mecze", n == sum(len(s["games"]) for s in scen), f"({n} meczow)")
        n_after = int(wp_db({}, "post", "list", "--post_type=sp_event", "--format=count"))
        check("baza domyslna (8090) nietknieta", n_before == n_after, f"({n_before} -> {n_after} meczow)")
        sizes = {p: (DBS / f"p{p}" / ".ht.sqlite").stat().st_size for p in PORTS}
        check("osobne pliki baz", len(sizes) == 2, "(" + ", ".join(f"p{p}: {s/1e6:.1f} MB" for p, s in sizes.items()) + ")")
    finally:
        for pr in procs:
            pr.terminate()
    print("\nT6:", "PRZESZEDL" if ok_all else "BLAD")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
