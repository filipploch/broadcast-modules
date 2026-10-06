"""T1b (tabele z prawdziwego sezonu vs tabele ze strony nalffutsal.pl) i T8b (import pelnego sezonu z nalffutsal.pl).

    python tests/wp/t1b_t8b.py --t1b   # sezon 61 (trwa): druzyny + mecze Dywizji A i B, porownanie z tabelami 147 i 111 na stronie
    python tests/wp/t1b_t8b.py --t8b   # sezon 59 (zakonczony): pelny import ze skladami, czasy i liczba zapytan
Tylko odczyt z nalffutsal.pl (1 s przerwy, _fields, per_page). Serwer lokalnego WP (8090) musi dzialac.
"""
import json, sys, time
import common, nalf_api as nalf
from common import OUT, REPO, install_test_plugin, wp
from nalf_import import import_season

SITE_TABLES = {19: 147, 20: 111}   # Dywizja A, Dywizja B (tabele na stronie, sezon 61)


def local_tables(imp, league_ids, criteria="t1-nalf"):
    cin = []
    for lg in league_ids:
        teams = sorted({imp["tmap"][t] for e in imp["events"] if e["_lg"] == lg for t in e["teams"] if t in imp["tmap"]})
        cin.append({"key": str(lg), "league": imp["leagues"][lg], "season": imp["season"], "teams": teams, "criteria": criteria})
    json.dump(cin, open(OUT / "calc_in.json", "w"))
    wp("eval-file", str(REPO / "tests/wp/calc_tables.php"), env={"BM_OUT": str(OUT)})
    return json.load(open(OUT / "calc_out.json"))


def main():
    mode = "--t8b" if "--t8b" in sys.argv else "--t1b"
    install_test_plugin(); wp("plugin", "activate", "advanced-h2h-for-sportspress", check=False)
    season, leagues, players = (61, [19, 20], False) if mode == "--t1b" else (59, [19, 20, 31], True)
    print(f"{mode}: sezon {season}, ligi {leagues}, zawodnicy: {players}", flush=True)
    imp = import_season(season, leagues, players)
    print(f"import: {imp['seconds']:.0f} s | zapytan do nalffutsal.pl: {imp['nalf_requests']} | zapytan do lokalnego WP: {imp['local_calls']} | bledow: {len(imp['fails'])}")
    for f in imp["fails"][:5]: print("   blad", f)
    tabs = local_tables(imp, [lg for lg in leagues if lg in (19, 20)])
    inv_t = {v: k for k, v in imp["tmap"].items()}; names = {t["id"]: t["title"]["rendered"] for t in imp["teams_src"]}
    json.dump({"tabs": tabs, "inv": {str(k): v for k, v in inv_t.items()}}, open(OUT / f"{mode[2:]}_tabs.json", "w"))
    diffs = 0
    if mode == "--t1b":
        for lg, tid in SITE_TABLES.items():
            site, _ = nalf.get(f"tables/{tid}", _fields="id,data")
            srows = [(int(k), v) for k, v in site["data"].items() if k != "0"]
            srows.sort(key=lambda kv: kv[1]["pos"])
            print(f"\n== Dywizja {'A' if lg == 19 else 'B'}: tabela strony (tables/{tid}) kontra lokalna ==")
            local = tabs[str(lg)]
            loc = [(inv_t[r["team"]], r) for r in local]
            print(f"{'poz':>3} {'druzyna (strona)':26} M Z R P GZ:GS RN PKT | lokalnie: druzyna  M Z R P GZ:GS RN PKT")
            for i in range(max(len(srows), len(loc))):
                s = srows[i] if i < len(srows) else None; l = loc[i] if i < len(loc) else None
                sv = lambda v: (v["m"], v["z"], v["r"], v["p"], v["gz"], v["gs"], v["roznica"], v["pkt"])
                lv = lambda r: tuple(str(r[k]) for k in ("p", "w", "d", "l", "f", "a", "gd", "pts"))
                same = s and l and s[0] == l[0] and tuple(map(str, sv(s[1]))) == lv(l[1])
                diffs += not same
                a = f"{s[1]['name'][:24]:26} {s[1]['m']} {s[1]['z']} {s[1]['r']} {s[1]['p']} {s[1]['gz']}:{s[1]['gs']} {s[1]['roznica']} {s[1]['pkt']}" if s else ""
                b = f"{names.get(l[0], l[0])[:24]:26} {' '.join(lv(l[1])[:4])} {lv(l[1])[4]}:{lv(l[1])[5]} {lv(l[1])[6]} {lv(l[1])[7]}" if l else ""
                print(f"{i+1:>3} {a:60} | {'OK ' if same else 'ROZNICA '}{b}")
        print(f"\nT1b: {'ZGODNE (kolejnosc i liczby)' if not diffs else str(diffs) + ' wierszy sie rozni'}; zapytan do nalffutsal.pl lacznie: {nalf.stats['requests']} (z pamieci podrecznej: {nalf.stats['cache_hits']})")
    else:
        print(f"\nT8b: sezon zakonczony zaimportowany: {len(imp['tmap'])} druzyn, {len(imp['pmap'])} zawodnikow, {len(imp['emap'])} meczow; "
              f"zapytan do nalffutsal.pl: {nalf.stats['requests']} (pamiec podreczna {nalf.stats['cache_hits']}), czas pobierania {nalf.stats['seconds']:.0f} s; lokalny import {imp['seconds']:.0f} s")
        for lg in tabs: print("Tabela lokalna lig", lg, [(names.get(inv_t[r['team']], '?')[:14], r['pts'], r['gd']) for r in tabs[lg][:5]], "...")
    sys.exit(1 if diffs or imp["fails"] else 0)


if __name__ == "__main__":
    main()
