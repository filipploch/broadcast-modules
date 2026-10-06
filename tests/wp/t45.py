"""T4 (minuty zdarzen) i T5 (pola wlasne w REST). Wymaga serwera WP na 8090 i wtyczki testowej."""
import time
from common import api, install_test_plugin
install_test_plugin(); st = str(int(time.time()))
lg = api("POST", "leagues", {"name": "T45 Liga " + st})["id"]; ss = api("POST", "seasons", {"name": "T45 Sezon " + st})["id"]
A = api("POST", "teams", {"title": "T45 A", "status": "publish", "leagues": [lg], "seasons": [ss]})["id"]
B = api("POST", "teams", {"title": "T45 B", "status": "publish", "leagues": [lg], "seasons": [ss]})["id"]
P = api("POST", "players", {"title": "T45 Gracz", "status": "publish", "teams": [A]})["id"]
ev = api("POST", "events", {"title": "T45", "status": "publish", "format": "league", "teams": [A, B], "leagues": [lg], "seasons": [ss]})["id"]
kits = {"home": {"shirt": "#ff0000", "shorts": "#ffffff"}, "away": {"shirt": "#0000ff"}, "gk": {"shirt": "#00aa00"}}
api("POST", f"teams/{A}", {"abbreviation": "TAA", "meta": {"bm_name14": "T45 A (14zn)", "bm_abbr3": "TAA", "bm_source": "nalf", "bm_source_id": "12345", "bm_kits": kits}})
g = api("GET", f"teams/{A}"); t5a = g["meta"]["bm_kits"] == kits and g["meta"]["bm_name14"] == "T45 A (14zn)" and g["abbreviation"] == "TAA"
api("POST", f"events/{ev}", {"meta": {"bm_locked": True, "bm_source_id": "m-777"}}); e = api("POST", f"events/{ev}", {"meta": {"bm_live": True}})
t5b = e["meta"]["bm_locked"] and e["meta"]["bm_live"] and e["meta"]["bm_source_id"] == "m-777"
tl = {str(A): {str(P): {"goals": ["12", "67"], "sub": ["60"]}}}
api("POST", f"events/{ev}", {"timeline": tl}); t4 = api("GET", f"events/{ev}")["timeline"] == tl
print("T5 druzyna:", t5a, "| T5 mecz (pola nie kasuja sie nawzajem):", t5b, "| T4 minuty:", t4)
raise SystemExit(0 if (t5a and t5b and t4) else 1)
