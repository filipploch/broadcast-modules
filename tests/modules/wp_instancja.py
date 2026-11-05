"""Jednorazowa instancja WP do testów na PRAWDZIWYM WP (port 8099, baza = kopia p8091, dane logowania z dane-api-nalf.json) i pomoce do budowania ligi testowej.

    with Instancja() as wp:
        k, o = wp.api('GET', 'bm/v1/table&league=1&season=2&mode=final')

Po wyjściu zatrzymuje TYLKO swój proces (po PID) i usuwa bazę p8099. Nie dotyka baz p8091/p8092 ani folderu transmisyjnego. Wymaga wolnego portu 8099.
Dodatek: Liga (budowanie ligi 6 drużyn z meczami przez REST) i oczekiwana_tabela() (niezależne wyliczenie tabeli wg zasad t1-nalf: punkty, bezpośrednie spotkania
w jednym przebiegu: punkty i różnica bramek w meczach między równymi, potem różnica ogółem, bramki, nazwa)."""
import base64
import json
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
WPL = REPO / 'wp-local'
PORT = 8099
BASE = f'http://127.0.0.1:{PORT}/index.php?rest_route=/'
DB_DIR = WPL / 'databases' / f'p{PORT}'


class Instancja:
    def __enter__(self):
        creds = json.loads((WPL / 'dane-api-nalf.json').read_text(encoding='utf-8-sig'))
        self.token = base64.b64encode(f"{creds['user']}:{creds['password']}".encode()).decode()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/', timeout=2):
                raise RuntimeError(f'Port {PORT} jest zajęty; zamknij to, co go używa.')
        except (urllib.error.URLError, OSError):
            pass
        if DB_DIR.exists():
            shutil.rmtree(DB_DIR)
        DB_DIR.mkdir(parents=True)
        for nazwa in ('.ht.sqlite', '.htaccess'):
            zrodlo = WPL / 'databases' / 'p8091' / nazwa
            if zrodlo.exists():
                shutil.copy2(zrodlo, DB_DIR / nazwa)
        self.proc = subprocess.Popen([str(WPL / 'php' / 'php.exe'), 'wp-cli.phar', '--path=wordpress', 'server', '--host=127.0.0.1', f'--port={PORT}'], cwd=str(WPL),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        for _ in range(60):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/', timeout=5):
                    return self
            except Exception:
                time.sleep(1)
        self.__exit__()
        raise RuntimeError('WP testowy nie wystartował w 60 s')

    def __exit__(self, *a):
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.proc.pid)], capture_output=True)
        time.sleep(1)
        shutil.rmtree(DB_DIR, ignore_errors=True)

    def api(self, metoda, trasa, dane=None, timeout=60):
        h = {'Content-Type': 'application/json', 'Authorization': 'Basic ' + self.token}
        req = urllib.request.Request(BASE + trasa, data=json.dumps(dane).encode() if dane is not None else None, headers=h, method=metoda)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode() or 'null')
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode())
            except ValueError:
                return e.code, None


class Liga:
    """Liga testowa: nowe termy ligi i sezonu, drużyny i mecze (format league) tworzone przez REST. Mecz: dict(h=indeks, g=indeks, wynik=(a, b) | None,
    stan=bm_state | None, na_zywo='g:o' | None, flaga=bool)."""

    NAZWY = ['Aaa', 'Bbb', 'Ccc', 'Ddd', 'Eee', 'Fff']

    def __init__(self, wp, n=6, nazwa='W8b'):
        self.wp = wp
        k, l = wp.api('POST', 'sportspress/v2/leagues', {'name': f'Liga {nazwa}', 'slug': f'w8b-liga-{nazwa.lower()}'})
        k2, s = wp.api('POST', 'sportspress/v2/seasons', {'name': f'Sezon {nazwa}', 'slug': f'w8b-sezon-{nazwa.lower()}'})
        assert k in (200, 201) and k2 in (200, 201), (k, l, k2, s)
        self.liga, self.sezon = l['id'], s['id']
        self.druzyny = []
        for nm in self.NAZWY[:n]:
            k, t = wp.api('POST', 'sportspress/v2/teams', {'title': nm, 'status': 'publish', 'leagues': [self.liga], 'seasons': [self.sezon]})
            assert k in (200, 201), (k, t)
            self.druzyny.append(t['id'])
        self.mecze = []

    def dodaj(self, h, g, wynik=None, stan=None, na_zywo=None, flaga=False, status='publish', data=None, liga=True, druzyny=None):
        teams = druzyny or [self.druzyny[h], self.druzyny[g]]
        cialo = {'title': f'{h}-{g}', 'status': status, 'date': data or '2026-10-01T12:00:00', 'teams': teams, 'format': 'league'}
        if liga:
            cialo.update(leagues=[self.liga], seasons=[self.sezon])
        meta = {}
        if stan is not None:
            meta['bm_state'] = stan
        if na_zywo is not None:
            meta['bm_live_score'] = na_zywo
        if flaga:
            meta['bm_zrodlo_brak'] = True
        if meta:
            cialo['meta'] = meta
        if wynik is not None:
            a, b = wynik
            o = ['win', 'loss'] if a > b else (['loss', 'win'] if a < b else ['draw', 'draw'])
            cialo['results'] = {str(teams[0]): {'goals': str(a), 'outcome': [o[0]]}, str(teams[1]): {'goals': str(b), 'outcome': [o[1]]}}
        k, e = self.wp.api('POST', 'sportspress/v2/events', cialo)
        assert k in (200, 201), (k, e)
        m = dict(id=e['id'], h=h, g=g, wynik=wynik, stan=stan, na_zywo=na_zywo, flaga=flaga)
        self.mecze.append(m)
        return e['id']

    def tabela(self, mode='final', **kw):
        return self.wp.api('GET', f'bm/v1/table&league={self.liga}&season={self.sezon}&mode={mode}' + ''.join(f'&{k}={v}' for k, v in kw.items()))


def liczone(mecze, mode):
    """Mecze liczone w tabeli wg reguł jawnego stanu: [(h, g, gole_h, gole_g)]."""
    wynik = []
    for m in mecze:
        stan = m['stan']
        if stan == 'zakonczony' or (stan is None and m['wynik'] is not None):
            if m['wynik'] is not None:
                wynik.append((m['h'], m['g'], *m['wynik']))
        elif stan == 'trwa' and mode == 'live' and not m['flaga'] and m['na_zywo']:
            a, b = (int(x) for x in m['na_zywo'].split(':'))
            wynik.append((m['h'], m['g'], a, b))
    return wynik


def oczekiwana_tabela(mecze, mode, nazwy=Liga.NAZWY):
    """Niezależne wyliczenie kolejności (indeksy drużyn) i statystyk: punkty 3/1/0; remis w punktach: mała tabela z meczów między równymi (jeden przebieg:
    punkty, różnica bramek), potem różnica bramek ogółem, bramki zdobyte, nazwa. Zwraca (kolejność, statystyki)."""
    st = {i: dict(p=0, w=0, d=0, l=0, f=0, a=0, pts=0) for i in range(len(nazwy))}
    gr = liczone(mecze, mode)
    for h, g, a, b in gr:
        for x, f, c in ((h, a, b), (g, b, a)):
            s = st[x]
            s['p'] += 1; s['f'] += f; s['a'] += c
            if f > c:
                s['w'] += 1; s['pts'] += 3
            elif f == c:
                s['d'] += 1; s['pts'] += 1
            else:
                s['l'] += 1
    for s in st.values():
        s['gd'] = s['f'] - s['a']

    def mala(grupa):
        m = {i: [0, 0] for i in grupa}
        for h, g, a, b in gr:
            if h in grupa and g in grupa:
                for x, f, c in ((h, a, b), (g, b, a)):
                    m[x][0] += 3 if f > c else (1 if f == c else 0)
                    m[x][1] += f - c
        return m
    kolejnosc = []
    for pts in sorted({s['pts'] for s in st.values()}, reverse=True):
        grupa = [i for i in st if st[i]['pts'] == pts]
        if len(grupa) > 1:
            mm = mala(set(grupa))
            grupa.sort(key=lambda i: (-mm[i][0], -mm[i][1], -st[i]['gd'], -st[i]['f'], nazwy[i]))
        kolejnosc += grupa
    return kolejnosc, st
