"""Źródło Garbarni: API Superscore (scorealarm-stats.freetls.fastly.net), tylko odczyt, przerwa między zapytaniami.

Endpointy (te same co w dotychczasowych scraperach modułu Garbarnia, parsowanie skopiowane jako czyste funkcje):
  fixtures/season?season-id=<id>&with-upcoming=yes   terminarz sezonu: mecze, drużyny (slug/hash), wyniki (końcowy i do przerwy), status
  teams/squad?team-id=<hash>                          kadra drużyny: zawodnicy (nazwisko, imię, numer, slug/hash)
Superscore NIE daje: numerów kolejek (round/week są puste), składów meczowych, strzelców, minut, kartek, zmian.
Identyfikatory źródła: drużyna = hash z seo_id (stały), zawodnik = player.id (jest u wszystkich; część zawodników ma "fake:player:<uuid>" i nie ma seo_id),
mecz = id meczu (tekst), liga = hash konkursu, sezon = id sezonu."""
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nazwy import podziel_nazwisko_imie

BASE = 'https://scorealarm-stats.freetls.fastly.net/v2/soccer/'
FIXTURES = BASE + 'fixtures/season/plsuperscore/pl-PL'
SQUAD = BASE + 'teams/squad/plsuperscore/pl-PL'
PRZERWA_S = 1.0
POZYCJE = ('goalkeepers', 'defenders', 'midfielders', 'attackers', 'other')
NIEROZPOCZETY, W_TOKU, ZAKONCZONY = 0, 1, 2


class SuperscoreApi:
    def __init__(self, cache_dir=None, przerwa=PRZERWA_S, opener=None):
        self.cache = Path(cache_dir) if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
        self.przerwa = przerwa
        self.opener = opener or urllib.request.urlopen
        self._ostatnie = 0.0
        self.zapytania = 0
        self.z_pamieci = 0

    def get(self, url, **params):
        pelny = url + ('?' + urllib.parse.urlencode(params) if params else '')
        plik = self.cache / (hashlib.md5(pelny.encode()).hexdigest() + '.json') if self.cache else None
        if plik is not None and plik.exists():
            self.z_pamieci += 1
            return json.loads(plik.read_text(encoding='utf-8'))
        czekaj = self.przerwa - (time.time() - self._ostatnie)
        if czekaj > 0:
            time.sleep(czekaj)
        req = urllib.request.Request(pelny, headers={'User-Agent': 'Mozilla/5.0 (compatible; broadcast-import/1.0)', 'Accept': 'application/json'})
        with self.opener(req, timeout=30) as r:
            surowe = r.read()
        self._ostatnie = time.time()
        self.zapytania += 1
        if not surowe:
            raise SystemExit(f'Superscore zwróciło pustą odpowiedź dla {pelny}: sprawdź identyfikator sezonu lub drużyny.')
        dane = json.loads(surowe.decode('utf-8'))
        if plik is not None:
            plik.write_text(json.dumps(dane, ensure_ascii=False), encoding='utf-8')
        return dane


def _hash(obj):
    seo = (obj or {}).get('seo_id') or {}
    return ((seo.get('hash') or {}).get('value')) or ''


def _slug(obj):
    seo = (obj or {}).get('seo_id') or {}
    return ((seo.get('slug') or {}).get('value')) or ''


def _nazwa_druzyny(t):
    n = (t.get('name') or '').strip()
    if n:
        return n
    for e in t.get('names') or []:
        if e.get('type') == 1:
            v = (e.get('value') or {}).get('string_value') or ''
            if v.strip():
                return v.strip()
    return ''


def _ostatnia_niedziela(rok, miesiac):
    ostatni = datetime(rok, miesiac, 31 if miesiac in (1, 3, 5, 7, 8, 10, 12) else 30)
    return ostatni - timedelta(days=(ostatni.weekday() + 1) % 7)


def czas_lokalny_pl(sekundy_utc):
    """Unix UTC -> czas lokalny Europa/Warszawa (reguła UE: lato od ost. niedzieli marca 01:00 UTC do ost. niedzieli października 01:00 UTC),
    jako 'RRRR-MM-DDTHH:MM:SS' (tak WP przechowuje datę meczu). Bez bazy stref czasowych (na Windowsie jej nie ma)."""
    utc = datetime.fromtimestamp(int(sekundy_utc), tz=timezone.utc).replace(tzinfo=None)
    start = _ostatnia_niedziela(utc.year, 3).replace(hour=1)
    koniec = _ostatnia_niedziela(utc.year, 10).replace(hour=1)
    przesuniecie = 7200 if start <= utc < koniec else 3600
    return (utc + timedelta(seconds=przesuniecie)).strftime('%Y-%m-%dT%H:%M:%S')


def _wynik(e, typ):
    for s in e.get('scores') or []:
        if s.get('type') == typ and s.get('team1') is not None and s.get('team2') is not None:
            return int(s['team1']), int(s['team2'])
    return None


def _wyniki_meczu(e, gospodarz, gosc):
    """Wynik końcowy i do przerwy -> results w formacie piłki nożnej SportsPressa (wynik, połowy, zwycięzca) albo {}."""
    if e.get('match_state') != ZAKONCZONY:
        return {}                                   # nierozpoczęty albo trwa: wyniku nie zapisujemy
    koniec = _wynik(e, 0)
    if koniec is None:
        return {}
    przerwa = _wynik(e, 1)
    wynik = {}
    for i, druzyna in enumerate((gospodarz, gosc)):
        gole, cudze = koniec[i], koniec[1 - i]
        r = {'goals': str(gole), 'outcome': ['win' if gole > cudze else 'loss' if gole < cudze else 'draw'], 'firsthalf': '', 'secondhalf': ''}
        if przerwa is not None:
            r['firsthalf'] = str(przerwa[i])
            r['secondhalf'] = str(gole - przerwa[i])
        wynik[druzyna] = r
    return wynik


def norm_mecz(e, liga_id, sezon_id):
    g, a = e.get('team1') or {}, e.get('team2') or {}
    gh, ah = _hash(g), _hash(a)
    sek = (e.get('match_date') or {}).get('seconds')
    return {'id': str(e['id']), 'date': czas_lokalny_pl(sek) if sek is not None else '', 'status': '', 'day': '', 'format': 'league',
            'minutes': '', 'leagues': [liga_id], 'seasons': [sezon_id], 'teams': [gh, ah], 'results': _wyniki_meczu(e, gh, ah),
            'players': [], 'performance': {}}


def norm_druzyna(t, nazwy, liga_id, sezon_id):
    h = _hash(t)
    kod = ((t.get('short_code') or {}).get('value') or '').strip()[:3].upper()
    return {'id': h, 'name': nazwy.get(h) or _nazwa_druzyny(t), 'slug': _slug(t), 'abbreviation': kod, 'leagues': [liga_id], 'seasons': [sezon_id]}


def norm_zawodnik(wpis, druzyna_hash, liga_id, sezon_id):
    p = wpis.get('player') or {}
    h = str(p.get('id') or '')            # wewnętrzny identyfikator zawodnika; część zawodników (wpisanych przez kluby) nie ma seo_id, ma id "fake:player:<uuid>"
    surowe = (p.get('name') or '').strip()
    if not h or not surowe:
        return None
    nazwisko, przecinek, imie = surowe.partition(',')
    nazwisko, imie = nazwisko.strip(), imie.strip()
    pewne = bool(przecinek) and bool(nazwisko) and bool(imie)          # Superscore zapisuje "Nazwisko, Imię": podział dokładny
    if not pewne:
        nazwisko, imie, pewne = podziel_nazwisko_imie(surowe)
    nazwa = f'{nazwisko} {imie}'.strip()                                 # "Nazwisko, Imię" -> "Nazwisko Imię" (tak jak zawodnicy NALF w WP)
    numer = str(wpis.get('shirt_number') or '').strip()
    return {'id': h, 'name': nazwa, 'last_name': nazwisko, 'first_name': imie, 'name_uncertain': not pewne, 'slug': _slug(p), 'number': int(numer) if numer.isdigit() else None, 'teams': [druzyna_hash],
            'leagues': [liga_id], 'seasons': [sezon_id]}


def pobierz_sezon(api, konf, z_zawodnikami=True, log=print):
    """Pobiera sezon z Superscore wg konfiguracji (sezon, liga: id/nazwa, nazwa_sezonu, nazwy drużyn) i normalizuje do wspólnego formatu importera."""
    sezon_id = konf['sezon']
    fx = api.get(FIXTURES, **{'season-id': sezon_id, 'with-upcoming': 'yes'})
    uwagi = []
    if fx.get('next_page'):
        uwagi.append('Superscore zgłasza kolejną stronę terminarza (next_page), której importer nie pobiera: lista meczów może być niepełna.')
    zdarzenia = fx.get('events') or []
    if not zdarzenia:
        raise SystemExit(f'Superscore nie zwróciło meczów dla sezonu {sezon_id}: sprawdź identyfikator sezonu w zrodla.json.')
    liga_id = konf['liga']['id']
    nazwy = konf.get('nazwy') or {}
    druzyny, widziane = [], set()
    for e in zdarzenia:
        for k in ('team1', 'team2'):
            t = e.get(k) or {}
            if _hash(t) and _hash(t) not in widziane:
                widziane.add(_hash(t))
                druzyny.append(norm_druzyna(t, nazwy, liga_id, sezon_id))
    mecze = [norm_mecz(e, liga_id, sezon_id) for e in zdarzenia if _hash(e.get('team1')) and _hash(e.get('team2'))]
    pominiete = len(zdarzenia) - len(mecze)
    if pominiete:
        uwagi.append(f'{pominiete} meczów bez identyfikatora drużyny pominięto.')
    zawodnicy, indeks = [], {}
    if z_zawodnikami:
        for d in druzyny:
            kadra = api.get(SQUAD, **{'team-id': d['id']})
            for klucz in POZYCJE:
                for wpis in kadra.get(klucz) or []:
                    z = norm_zawodnik(wpis, d['id'], liga_id, sezon_id)
                    if z is None:
                        continue
                    if z['id'] in indeks:                                       # zawodnik w kadrach dwóch drużyn
                        if d['id'] not in indeks[z['id']]['teams']:
                            indeks[z['id']]['teams'].append(d['id'])
                        continue
                    indeks[z['id']] = z
                    zawodnicy.append(z)
    log(f'  źródło: {len(druzyny)} drużyn, {len(zawodnicy)} zawodników, {len(mecze)} meczów '
        f'(zapytań do strony: {api.zapytania}, z pamięci: {api.z_pamieci})')
    return {'sezon': {'id': sezon_id, 'name': konf['nazwa_sezonu'], 'slug': ''},
            'ligi': {liga_id: {'id': liga_id, 'name': konf['liga']['nazwa'], 'slug': ''}},
            'druzyny': druzyny, 'zawodnicy': zawodnicy, 'mecze': mecze, 'uwagi': uwagi}
