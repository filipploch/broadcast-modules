"""T8: import pelnego sezonu przez REST: 14 druzyn, 182 mecze (rewanze), 15 zawodnikow na druzyne, kadra + gole w kazdym meczu."""
import json, random, sys, time
import common as lib
from common import api
rnd = random.Random(8); t0 = time.time(); stamp = str(int(t0)); N = 14
def phase(name, t): print(f"{name}: {time.time()-t:.1f}s, zadan narastajaco {lib.calls}"); return time.time()
lg = api("POST","leagues",{"name":"T8 Liga "+stamp})["id"]; ss = api("POST","seasons",{"name":"T8 Sezon "+stamp})["id"]
t = phase("liga+sezon", t0)
teams = [api("POST","teams",{"title":f"T8 Druzyna {i:02d}","status":"publish","leagues":[lg],"seasons":[ss]})["id"] for i in range(N)]
t = phase(f"{N} druzyn", t)
squad = {tm: [api("POST","players",{"title":f"T8 Gracz {i:02d}-{j:02d}","status":"publish","leagues":[lg],"seasons":[ss],"teams":[tm]})["id"] for j in range(15)] for i,tm in enumerate(teams)}
t = phase(f"{N*15} zawodnikow", t)
fails = 0; n = 0
for rnd_no, (h, a) in enumerate([(h,a) for h in teams for a in teams if h != a]):
    hg, ag = rnd.choice([0,1,2,3,4]), rnd.choice([0,1,2,3])
    perf = {}; plist = [0]
    for tm, g in ((h,hg),(a,ag)):
        scorers = [rnd.choice(squad[tm][:10]) for _ in range(g)]
        perf[str(tm)] = {str(p): {"number":str(k+1),"status":"lineup" if k<10 else "sub","goals":str(scorers.count(p))} for k,p in enumerate(squad[tm][:12])}
        plist += squad[tm][:12] + [0]
    oh = "win" if hg>ag else "draw" if hg==ag else "loss"; oa = {"win":"loss","draw":"draw","loss":"win"}[oh]
    r = api("POST","events",{"title":f"T8 {h}-{a}","status":"publish","date":f"2026-0{1+rnd_no//60}-{1+rnd_no%28:02d}T18:00:00","format":"league","leagues":[lg],"seasons":[ss],
        "teams":[h,a],"players":plist,"results":{str(h):{"goals":str(hg),"outcome":[oh]},str(a):{"goals":str(ag),"outcome":[oa]}},"performance":perf})
    n += 1; fails += "id" not in r
t = phase(f"{n} meczow (porazek: {fails})", t)
print(f"RAZEM: {time.time()-t0:.1f}s, {lib.calls} zadan; sredni czas zadania {1000*(time.time()-t0)/lib.calls:.0f} ms")
