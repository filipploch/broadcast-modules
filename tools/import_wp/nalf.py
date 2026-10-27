"""Źródło NALF: API SportsPressa na nalffutsal.pl (tylko odczyt, przerwa między zapytaniami, pamięć podręczna na dysku).

Normalizacja: z odpowiedzi API powstają proste słowniki (identyfikatory ze źródła), które importer zapisuje do WP. Z `performance` zostają
tylko standardowe statystyki zawodnika (bez `position`: to identyfikatory pozycji z innej strony)."""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

from nazwy import oczyść, podziel_nazwisko_imie

BASE = 'https://nalffutsal.pl/index.php?rest_route=/sportspress/v2/'
PRZERWA_S = 1.0
STATYSTYKI = ('goals', 'assists', 'yellowcards', 'redcards', 'owngoals', 'number', 'status', 'sub')


class NalfApi:
    def __init__(self, cache_dir=None, przerwa=PRZERWA_S, base=BASE, opener=None):
        self.cache = Path(cache_dir) if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
        self.przerwa = przerwa
        self.base = base
        self.opener = opener or urllib.request.urlopen
        self._ostatnie = 0.0
        self.zapytania = 0
        self.z_pamieci = 0

    def get(self, zasob, **params):
        q = '&'.join(f'{k}={v}' for k, v in params.items())
        url = self.base + zasob + ('&' + q if q else '')
        plik = self.cache / (hashlib.md5(url.encode()).hexdigest() + '.json') if self.cache else None
        if plik is not None and plik.exists():
            self.z_pamieci += 1
            d = json.loads(plik.read_text(encoding='utf-8'))
            return d['body'], d['headers']
        czekaj = self.przerwa - (time.time() - self._ostatnie)
        if czekaj > 0:
            time.sleep(czekaj)
        req = urllib.request.Request(url, headers={'User-Agent': 'broadcast-modules-import/1.0 (odczyt)', 'Accept': 'application/json'})
        with self.opener(req, timeout=60) as r:
            body = json.loads(r.read().decode('utf-8'))
            headers = {k.lower(): v for k, v in r.headers.items()}
        self._ostatnie = time.time()
        self.zapytania += 1
        if plik is not None:
            plik.write_text(json.dumps({'body': body, 'headers': headers}, ensure_ascii=False), encoding='utf-8')
        return body, headers

    def get_all(self, zasob, **params):
        wynik, strona = [], 1
        while True:
            body, h = self.get(zasob, per_page=100, page=strona, **params)
            wynik += body
            if strona >= int(h.get('x-wp-totalpages', 1)):
                return wynik
            strona += 1


def _tekst(v):
    return '' if v is None else str(v)


def norm_taksonomia(x):
    return {'id': int(x['id']), 'name': x['name'], 'slug': x.get('slug') or ''}


def norm_druzyna(t):
    return {'id': int(t['id']), 'name': oczyść(t['title']['rendered']), 'slug': t.get('slug') or '', 'abbreviation': _tekst(t.get('abbreviation')),
            'leagues': sorted(int(i) for i in t.get('leagues') or []), 'seasons': sorted(int(i) for i in t.get('seasons') or [])}


def norm_zawodnik(p):
    numer = _tekst(p.get('number')).strip()
    nazwa = oczyść(p['title']['rendered'])
    nazwisko, imie, pewne = podziel_nazwisko_imie(nazwa)
    return {'id': int(p['id']), 'name': nazwa, 'last_name': nazwisko, 'first_name': imie, 'name_uncertain': not pewne,
            'slug': p.get('slug') or '', 'number': int(numer) if numer.isdigit() else None,
            'teams': [int(i) for i in p.get('teams') or [] if int(i)], 'leagues': sorted(int(i) for i in p.get('leagues') or []),
            'seasons': sorted(int(i) for i in p.get('seasons') or [])}


def _norm_wiersz(w):
    return {k: _tekst(w.get(k)) for k in STATYSTYKI if k in w}


def norm_mecz(e):
    res = e.get('results')
    wyniki = {}
    if isinstance(res, dict):                      # nierozegrany mecz ma w results pustą listę
        for team, v in res.items():
            if team == '0' or not isinstance(v, dict):
                continue
            wyniki[str(int(team))] = {'firsthalf': _tekst(v.get('firsthalf')), 'secondhalf': _tekst(v.get('secondhalf')),
                                      'goals': _tekst(v.get('goals')), 'outcome': [str(o) for o in (v.get('outcome') or [])]}
    perf = {}
    if isinstance(e.get('performance'), dict):     # w meczu bez składu performance bywa listą
        for team, rows in e['performance'].items():
            if team == '0' or not isinstance(rows, dict):
                continue
            perf[str(int(team))] = {str(int(pl)): _norm_wiersz(w) for pl, w in rows.items() if pl != '0' and isinstance(w, dict)}
    return {'id': int(e['id']), 'date': e.get('date') or '', 'status': e.get('status') or '', 'day': _tekst(e.get('day')),
            'format': e.get('format') or 'league', 'minutes': _tekst(e.get('minutes')),
            'leagues': sorted(int(i) for i in e.get('leagues') or []), 'seasons': sorted(int(i) for i in e.get('seasons') or []),
            'teams': [int(i) for i in e.get('teams') or []], 'results': wyniki,
            'players': [int(i) for i in e.get('players') or []], 'performance': perf}


def pobierz_sezon(api, sezon_id, z_zawodnikami=True, log=print):
    """Pobiera z API jeden sezon: taksonomie, drużyny, zawodników i mecze (znormalizowane)."""
    sezony = {int(x['id']): norm_taksonomia(x) for x in api.get_all('seasons', _fields='id,name,slug')}
    if sezon_id not in sezony:
        raise SystemExit(f'Źródło nie ma sezonu o id {sezon_id}. Dostępne: ' + ', '.join(f'{i} ({s["name"]})' for i, s in sorted(sezony.items())))
    ligi = {int(x['id']): norm_taksonomia(x) for x in api.get_all('leagues', _fields='id,name,slug')}
    druzyny = [norm_druzyna(t) for t in api.get_all('teams', seasons=sezon_id, _fields='id,slug,title,abbreviation,leagues,seasons')]
    mecze = [norm_mecz(e) for e in api.get_all(
        'events', seasons=sezon_id, _fields='id,date,status,format,day,minutes,leagues,seasons,teams,players,results,performance')]
    zawodnicy = []
    if z_zawodnikami:
        zawodnicy = [norm_zawodnik(p) for p in api.get_all('players', seasons=sezon_id, _fields='id,slug,title,number,teams,leagues,seasons')]
    log(f'  źródło: {len(druzyny)} drużyn, {len(zawodnicy)} zawodników, {len(mecze)} meczów '
        f'(zapytań do strony: {api.zapytania}, z pamięci: {api.z_pamieci})')
    uzyte = {l for m in mecze for l in m['leagues']} | {l for t in druzyny for l in t['leagues']}
    return {'sezon': sezony[sezon_id], 'ligi': {i: ligi[i] for i in sorted(uzyte) if i in ligi},
            'druzyny': druzyny, 'zawodnicy': zawodnicy, 'mecze': mecze}
