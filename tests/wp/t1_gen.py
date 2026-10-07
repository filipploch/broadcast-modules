"""T1: generuje losowe sezony i liczy kolejnosc referencyjna kodem z repozytorium (standings.py + sort_group NALF/MZPN)."""
import ast, importlib.util, json, random, sys, types, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import OUT
ROOT = pathlib.Path(__file__).resolve().parents[2] / "modules"

# standings.py ladowany z pliku (pure python)
spec = importlib.util.spec_from_file_location("standings", ROOT / "core/utils/standings.py")
st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
core = types.ModuleType("core"); utils = types.ModuleType("core.utils"); sys.modules.update({"core": core, "core.utils": utils, "core.utils.standings": st})

def load_sort_group(path):
    src = (ROOT / path).read_text(encoding="utf-8")
    fn = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "sort_group"][0]
    ns = {}; exec(compile(ast.Module([fn], []), path, "exec"), ns); return ns["sort_group"]
SORT = {"NALF": load_sort_group("futsal_nalf/app/models/game.py"), "MZPN": load_sort_group("garbarnia/app/models/game.py")}

class G:
    is_finished = True
    def __init__(s, h, a, hg, ag): s.home_team_id, s.away_team_id, s.hg, s.ag = h, a, hg, ag
    def _st(s, gf, ga): return {"points": 3 if gf > ga else 1 if gf == ga else 0, "goals_scored": gf, "goals_lost": ga, "wins": int(gf > ga)}
    def get_home_team_stats(s): return s._st(s.hg, s.ag)
    def get_away_team_stats(s): return s._st(s.ag, s.hg)

def table(teams, games, rule):
    rows = {t: dict(team_id=t, points=0, wins=0, goals_scored=0, goals_lost=0) for t in teams}
    for g in games:
        for tid, s in ((g.home_team_id, g.get_home_team_stats()), (g.away_team_id, g.get_away_team_stats())):
            r = rows[tid]; r["points"] += s["points"]; r["wins"] += s["wins"]; r["goals_scored"] += s["goals_scored"]; r["goals_lost"] += s["goals_lost"]
    lst = list(rows.values())
    for r in lst: r["goal_difference"] = r["goals_scored"] - r["goals_lost"]
    return [r["team_id"] for r in st.apply_tiebreakers(lst, games, SORT[rule])], lst

def fully_tied(order, lst, games, rule):
    """czy sasiednie druzyny sa nierozroznialne wszystkimi kryteriami (wtedy kolejnosc zalezy od losowania)"""
    rows = {r["team_id"]: r for r in lst}; tied = False
    for i in range(len(order) - 1):
        a, b = rows[order[i]], rows[order[i + 1]]
        if a["points"] != b["points"]: continue
        ids = [a["team_id"], b["team_id"]]
        grp = [r for r in lst if r["points"] == a["points"]]
        mini = st.compute_mini_table([r["team_id"] for r in grp], games)
        def key(r):
            k = (mini[r["team_id"]]["points"], mini[r["team_id"]]["gd"], r["goal_difference"], r["goals_scored"])
            if rule == "MZPN": k += (r["wins"], st.count_away_wins(r["team_id"], games))
            return k
        if key(a) == key(b): tied = True
    return tied

def gen(seed, n_teams=6, double=False, tight=False):
    rnd = random.Random(seed); teams = list(range(1, n_teams + 1)); games = []
    pairs = [(a, b) for a in teams for b in teams if a < b]
    for a, b in pairs:
        ms = [(a, b), (b, a)] if double else [(a, b) if rnd.random() < .5 else (b, a)]
        for h, aw in ms: games.append(G(h, aw, *( [rnd.choice([0, 1, 1, 2]), rnd.choice([0, 1, 1, 2])] if tight else [rnd.choice([0, 0, 1, 1, 2, 3]), rnd.choice([0, 0, 1, 1, 2, 3])] )))
    return teams, games

if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    out = []
    for i in range(N):
        teams, games = gen(1000 + i, n_teams=5 + i % 4, double=(i % 2 == 0), tight=(i >= 60))
        sc = {"id": i, "teams": teams, "games": [[g.home_team_id, g.away_team_id, g.hg, g.ag] for g in games], "ref": {}}
        for rule in ("NALF", "MZPN"):
            order, lst = table(teams, games, rule)
            sc["ref"][rule] = {"order": order, "undetermined": fully_tied(order, lst, games, rule)}
        out.append(sc)
    json.dump(out, open(OUT / "t1_scen.json", "w"))
    print(N, "scenariuszy;", "z remisem punktowym:", sum(any(s["ref"][r]["order"] for r in ["NALF"]) for s in out))
