"""T1: porownanie kolejnosci tabeli SportsPress + Advanced H2H z kodem Pythona (NALF i MZPN) na losowych sezonach.

Uzycie (z dowolnego katalogu, serwer WP nie jest potrzebny):
    python tests/wp/run_t1.py            # szybko: 30 losowych + 10 celowanych (ok. 2 min)
    python tests/wp/run_t1.py --pelny    # 140 losowych + 15 celowanych (ok. 7 min)
Kod wyjscia 0 = pelna zgodnosc, 1 = sa roznice.
"""
import json, subprocess, sys
import t1_gen as g
from common import OUT, REPO, install_test_plugin, wp


def scenario(i, teams, games):
    sc = {"id": i, "teams": teams, "games": [[x.home_team_id, x.away_team_id, x.hg, x.ag] for x in games], "ref": {}}
    for rule in ("NALF", "MZPN"):
        order, lst = g.table(teams, games, rule)
        sc["ref"][rule] = {"order": order, "undetermined": g.fully_tied(order, lst, games, rule)}
    return sc


def build(n_random, n_targeted):
    out = []
    for i in range(n_random):  # druga polowa: niskie wyniki, wiecej remisow
        teams, games = g.gen(1000 + i, n_teams=5 + i % 4, double=(i % 2 == 0), tight=(i >= n_random // 2))
        out.append(scenario(len(out), teams, games))
    seed = 20000
    found = 0
    while found < n_targeted:  # sezony, w ktorych kryteria MZPN (wygrane, wygrane wyjazdowe) zmieniaja kolejnosc wzgledem NALF
        seed += 1
        teams, games = g.gen(seed, n_teams=4 + seed % 3, double=(seed % 2 == 0), tight=True)
        o1, _ = g.table(teams, games, "NALF"); o2, l2 = g.table(teams, games, "MZPN")
        if o1 != o2 and not g.fully_tied(o2, l2, games, "MZPN"):
            out.append(scenario(len(out), teams, games)); found += 1
    return out


def main():
    full = "--pelny" in sys.argv
    scen = build(140 if full else 30, 15 if full else 10)
    json.dump(scen, open(OUT / "t1_scen.json", "w"))
    install_test_plugin()
    wp("plugin", "activate", "advanced-h2h-for-sportspress", check=False)
    print(f"{len(scen)} scenariuszy, liczenie w SportsPress...", flush=True)
    print(wp("eval-file", str(REPO / "tests/wp/t1_run.php"), env={"BM_OUT": str(OUT)}).strip())
    res = json.load(open(OUT / "t1_out.json")); res = {str(k): v for k, v in (res.items() if isinstance(res, dict) else enumerate(res))}
    bad_total = 0
    for rule in ("NALF", "MZPN"):
        ok = und = 0; bad = []
        for s in scen:
            sp, ref = res[str(s["id"])][rule], s["ref"][rule]
            if sp == ref["order"]: ok += 1
            elif ref["undetermined"]: und += 1
            else: bad.append((s["id"], ref["order"], sp))
        bad_total += len(bad)
        print(f"{rule}: {len(scen)} scen., zgodne {ok}, roznica tylko przy pelnym remisie {und}, ROZNICE {len(bad)}")
        for b in bad[:5]: print("   scen", b[0], "ref", b[1], "SportsPress", b[2])
    sys.exit(1 if bad_total else 0)


if __name__ == "__main__":
    main()
