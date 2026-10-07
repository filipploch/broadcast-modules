"""T3: zapis wyniku, kadry meczowej i statystyk przez REST; odczyt wyliczonych pol. Wymaga serwera WP na 8090."""
import time
from common import api, wp
st = str(int(time.time()))
lg = api("POST", "leagues", {"name": "T3 Liga " + st})["id"]; ss = api("POST", "seasons", {"name": "T3 Sezon " + st})["id"]
A = api("POST", "teams", {"title": "T3 A", "status": "publish", "leagues": [lg], "seasons": [ss]})["id"]
B = api("POST", "teams", {"title": "T3 B", "status": "publish", "leagues": [lg], "seasons": [ss]})["id"]
pl = [api("POST", "players", {"title": f"T3 Gracz {i}", "status": "publish", "leagues": [lg], "seasons": [ss], "teams": [A if i < 2 else B]})["id"] for i in range(4)]
a, b = str(A), str(B)
ev = api("POST", "events", {"title": "T3 A-B", "status": "publish", "date": "2026-10-01T18:00:00", "format": "league", "leagues": [lg], "seasons": [ss],
    "teams": [A, B], "players": [0, pl[0], pl[1], 0, pl[2], pl[3]],
    "results": {a: {"firsthalf": "1", "secondhalf": "1", "goals": "2", "outcome": ["win"]}, b: {"firsthalf": "0", "secondhalf": "1", "goals": "1", "outcome": ["loss"]}},
    "performance": {a: {"0": {"goals": "0"}, str(pl[0]): {"number": "9", "status": "lineup", "goals": "2"}, str(pl[1]): {"number": "10", "status": "sub", "goals": "0"}},
                    b: {"0": {"goals": "0"}, str(pl[2]): {"number": "7", "status": "lineup", "goals": "1"}, str(pl[3]): {"number": "8", "status": "sub", "goals": "0"}}}})
e = api("GET", f"events/{ev['id']}")
zapis = e["main_results"] == ["2", "1"] and e["winner"] == A and e["performance"][a][str(pl[0])]["status"] == "lineup" and e["performance"][a][str(pl[1])]["status"] == "sub"
# statystyki sezonowe: licza sie dopiero po ustawieniu meta sp_leagues (REST jej nie wystawia - wniosek T3)
wp("eval", f"update_post_meta({pl[0]},'sp_leagues',[{lg}=>[{ss}=>{A}]]);")
stats = api("GET", f"players/{pl[0]}")["statistics"][str(lg)]
row = stats[str(ss)]
przeliczone = row["goals"] == 2 and row["appearances"] == "1"
print("T3 zapis/odczyt:", zapis, "| statystyki sezonu po ustawieniu sp_leagues:", przeliczone)
raise SystemExit(0 if zapis and przeliczone else 1)
