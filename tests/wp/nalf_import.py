"""Import sezonu z nalffutsal.pl (tylko odczyt zrodla) do lokalnego WP przez REST. Uzywany przez t1b_t8b.py."""
import time
import common
from common import api
import nalf_api as nalf

EV_FIELDS = "id,date,status,format,day,minutes,leagues,seasons,teams,players,results,performance"


def _pmap(m, ids):
    return [m[i] for i in ids if i in m]


def import_season(season_id, league_ids, with_players, log=print):
    """Zwraca dict: lokalne id lig/sezonu, mapy druzyn/zawodnikow, liczby zapytan i czasy."""
    stamp = str(int(time.time()))
    t0 = time.time(); calls0 = common.calls; n0 = nalf.stats["requests"]
    s_src, _ = nalf.get("seasons", per_page=100, _fields="id,name")
    l_src, _ = nalf.get("leagues", per_page=100, _fields="id,name")
    sname = {x["id"]: x["name"] for x in s_src}[season_id]; lname = {x["id"]: x["name"] for x in l_src}
    loc_season = api("POST", "seasons", {"name": f"{sname} [{stamp}]"})["id"]
    loc_league = {lg: api("POST", "leagues", {"name": f"{lname[lg]} [{stamp}]"})["id"] for lg in league_ids}
    # druzyny
    teams_src = nalf.get_all("teams", seasons=season_id, _fields="id,title,abbreviation,leagues")
    tmap = {}
    for t in teams_src:
        r = api("POST", "teams", {"title": t["title"]["rendered"], "status": "publish", "abbreviation": t.get("abbreviation") or "",
                                  "leagues": [loc_league[l] for l in t["leagues"] if l in loc_league], "seasons": [loc_season],
                                  "meta": {"bm_source": "nalf", "bm_source_id": str(t["id"])}})
        tmap[t["id"]] = r["id"]
    log(f"  druzyny: {len(tmap)}")
    # zawodnicy
    pmap = {}; pfails = []
    if with_players:
        players_src = []
        for lg in league_ids:
            players_src += nalf.get_all("players", leagues=lg, seasons=season_id, _fields="id,title,number,teams")
        seen = set()
        for p in players_src:
            if p["id"] in seen: continue
            seen.add(p["id"])
            body = {"title": p["title"]["rendered"], "status": "publish",
                    "teams": _pmap(tmap, p.get("teams") or []), "leagues": list(loc_league.values()), "seasons": [loc_season]}
            if str(p.get("number") or "").isdigit(): body["number"] = int(p["number"])
            r = api("POST", "players", body)
            if "id" in r: pmap[p["id"]] = r["id"]
            else: pfails.append((p["id"], str(r)[:150]))
        log(f"  zawodnicy: {len(pmap)}, bledow: {len(pfails)}")
    # mecze
    events = []
    for lg in league_ids:
        events += [dict(e, _lg=lg) for e in nalf.get_all("events", leagues=lg, seasons=season_id, _fields=EV_FIELDS)]
    fails = []; emap = {}
    for e in events:
        tm = _pmap(tmap, e["teams"])
        if len(tm) != len(e["teams"]):
            fails.append((e["id"], "nieznana druzyna")); continue
        res = {str(tmap[int(k)]): v for k, v in (e.get("results") or {}).items() if k != "0" and int(k) in tmap}
        body = {"title": " - ".join(str(x) for x in tm), "status": "publish", "date": e["date"], "format": e["format"] or "league", "day": e.get("day") or "",
                "leagues": [loc_league[e["_lg"]]], "seasons": [loc_season], "teams": tm, "meta": {"bm_source": "nalf", "bm_source_id": str(e["id"])}}
        if e.get("minutes"): body["minutes"] = int(e["minutes"])
        if res: body["results"] = res
        if with_players and isinstance(e.get("performance"), dict) and e["performance"]:
            body["performance"] = {str(tmap[int(t)]): {("0" if p == "0" else str(pmap[int(p)])): v for p, v in rows.items() if p == "0" or int(p) in pmap} if isinstance(rows, dict) else {}
                                   for t, rows in e["performance"].items() if t != "0" and int(t) in tmap}
            body["players"] = [pmap[p] if p else 0 for p in e.get("players") or [] if p == 0 or p in pmap]
        r = api("POST", "events", body)
        if "id" in r: emap[e["id"]] = r["id"]
        else: fails.append((e["id"], str(r)[:150]))
    log(f"  mecze: {len(emap)} zapisanych, {len(fails)} bledow")
    return {"season": loc_season, "leagues": loc_league, "tmap": tmap, "pmap": pmap, "emap": emap, "events": events, "fails": fails + pfails,
            "teams_src": teams_src, "seconds": time.time() - t0, "local_calls": common.calls - calls0, "nalf_requests": nalf.stats["requests"] - n0}
