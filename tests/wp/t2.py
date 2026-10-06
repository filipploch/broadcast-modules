"""T2: tabela oficjalna i wirtualna (mecz trwajacy). Wymaga serwera WP na 8090 i wtyczki testowej."""
import time
from common import api, install_test_plugin, wp
install_test_plugin(); st = str(int(time.time()))
lg = api("POST", "leagues", {"name": "T2 Liga " + st})["id"]; ss = api("POST", "seasons", {"name": "T2 Sezon " + st})["id"]
T = {n: api("POST", "teams", {"title": "T2 " + n, "status": "publish", "leagues": [lg], "seasons": [ss]})["id"] for n in "ABC"}
def ev(h, a, hg, ag, live=False, day=1):
    oh = "win" if hg > ag else "draw" if hg == ag else "loss"; oa = {"win": "loss", "draw": "draw", "loss": "win"}[oh]
    return api("POST", "events", {"title": f"T2 {h}-{a}", "status": "publish", "date": f"2026-09-{day:02d}T18:00:00", "format": "league",
        "leagues": [lg], "seasons": [ss], "teams": [T[h], T[a]], "meta": {"bm_live": live},
        "results": {str(T[h]): {"goals": str(hg), "outcome": [oh]}, str(T[a]): {"goals": str(ag), "outcome": [oa]}}})
ev("A", "B", 1, 0, day=1); ev("B", "C", 2, 2, day=2); ev("A", "C", 0, 1, live=True, day=3)
php = (f"$tb=wp_insert_post(['post_type'=>'sp_table','post_title'=>'T2 tabela','post_status'=>'publish']);update_post_meta($tb,'sp_select','manual');"
       f"foreach([{T['A']},{T['B']},{T['C']}] as $t) add_post_meta($tb,'sp_team',$t);wp_set_object_terms($tb,[{lg}],'sp_league');wp_set_object_terms($tb,[{ss}],'sp_season');echo $tb;")
tb = wp("eval", php).strip()
r = api("GET", f"table/{tb}", ns="bm/v1")
got = {k: [(x["name"][-1], x["pts"]) for x in r[k]] for k in ("official", "virtual")}
print(got)
ok = got["official"] == [("A", "3"), ("C", "1"), ("B", "1")] and got["virtual"] == [("C", "4"), ("A", "3"), ("B", "1")]
print("T2:", "PRZESZEDL" if ok else "BLAD"); raise SystemExit(0 if ok else 1)
