"""Klient tylko-do-odczytu API nalffutsal.pl: przerwa 1 s miedzy zadaniami, licznik, pamiec podreczna na dysku (poza gitem)."""
import hashlib, json, time, urllib.request, urllib.error
from common import OUT

BASE = "https://nalffutsal.pl/index.php?rest_route=/sportspress/v2/"
CACHE = OUT / "nalf-cache"; CACHE.mkdir(exist_ok=True)
stats = {"requests": 0, "seconds": 0.0, "cache_hits": 0}
_last = [0.0]


def get(resource, **params):
    """GET <resource>?<params>. Zwraca (json, naglowki). Pole _fields i per_page podawac zawsze."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = BASE + resource + ("&" + q if q else "")
    key = CACHE / (hashlib.md5(url.encode()).hexdigest() + ".json")
    if key.exists():
        stats["cache_hits"] += 1
        d = json.loads(key.read_text(encoding="utf-8")); return d["body"], d["headers"]
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    t = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "broadcast-modules-test/1.0 (odczyt)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read().decode("utf-8")); headers = {k.lower(): v for k, v in r.headers.items()}
    _last[0] = time.time(); stats["requests"] += 1; stats["seconds"] += _last[0] - t
    key.write_text(json.dumps({"body": body, "headers": headers}), encoding="utf-8")
    return body, headers


def get_all(resource, **params):
    """Wszystkie strony (per_page <= 100); zwraca liste."""
    params = {"per_page": 100, **params}; out = []; page = 1
    while True:
        body, h = get(resource, page=page, **params)
        out += body
        if page >= int(h.get("x-wp-totalpages", 1)): return out
        page += 1
