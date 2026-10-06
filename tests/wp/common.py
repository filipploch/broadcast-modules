"""Wspolne narzedzia testow WP/SportsPress (E0). Uruchamiane z dowolnego katalogu."""
import base64, json, pathlib, shutil, subprocess, time, urllib.error, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
WP_LOCAL = REPO / "wp-local"
OUT = WP_LOCAL / "tests-out"          # wyniki posrednie (poza gitem)
PHP = WP_LOCAL / "php" / "php.exe"
WPCLI = WP_LOCAL / "wp-cli.phar"
WP_PATH = WP_LOCAL / "wordpress"
BASE = "http://127.0.0.1:8090"
OUT.mkdir(exist_ok=True)


def wp(*args, env=None, check=True):
    """Uruchamia WP-CLI na lokalnej instalacji; zwraca stdout."""
    import os
    r = subprocess.run([str(PHP), str(WPCLI), f"--path={WP_PATH}", *args], capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, **(env or {})})
    if check and r.returncode:
        raise RuntimeError(r.stderr or r.stdout)
    return r.stdout


def install_test_plugin():
    """Kopiuje wtyczke testowa z repo (wp-plugin/bm-test) do mu-plugins instalacji testowej."""
    dst = WP_PATH / "wp-content" / "mu-plugins"
    dst.mkdir(exist_ok=True)
    shutil.copy(REPO / "wp-plugin" / "bm-test" / "bm-test.php", dst / "bm-test.php")


def _app_password():
    f = WP_LOCAL / "DANE-LOGOWANIA.txt"
    return [l.split(": ", 1)[1].strip() for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("Haslo aplikacji")][0]


calls = 0


def api(method, path, body=None, ns="sportspress/v2", base=BASE):
    """Zadanie REST do lokalnego WP (z haslem aplikacji). Zwraca JSON albo {'_http':kod,'_body':...}."""
    global calls
    calls += 1
    url = f"{base}/?rest_route=/{ns}/{path.lstrip('/')}"
    if "?" in path:
        p, q = path.split("?", 1)
        url = f"{base}/?rest_route=/{ns}/{p.lstrip('/')}&{q}"
    auth = "Basic " + base64.b64encode(f"operator:{_app_password()}".encode()).decode()
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": auth, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode()[:500]}
