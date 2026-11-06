"""Próba ręczna W8b: przygotowanie przypadków brzegowych tabeli na KOPII WP (port 8099, uruchomionej przez uruchom-w8a.bat) dla Dywizji A.

    python tests/modules/proba_tabela_przygotuj.py duplikat | obca | flaga | kosz | wszystko | cofnij

Działa WYŁĄCZNIE na porcie 8099 (kopia bazy; instancje 8091/8092 nie są dotykane). Zmiany: duplikat meczu (drugi wpis z tą samą parą i wynikiem), mecz z drużyną spoza ligi,
flaga bm_zrodlo_brak na zakończonym meczu, mecz przeniesiony do kosza. Co zrobiono, zapisuje w pliku stanu, z którego „cofnij” przywraca kopię (kosz, flagi) i usuwa dodane wpisy.
Po próbie i tak wystarczy zatrzymać próbę (zatrzymaj-w8a.bat usuwa całą kopię bazy)."""
import base64
import json
import pathlib
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
WPL = REPO / 'wp-local'
PORT = 8099
STAN = WPL / 'probe-b-minuta' / 'proba-tabela-stan.json'


def api_8099(metoda, trasa, dane=None):
    creds = json.loads((WPL / 'dane-api-nalf.json').read_text(encoding='utf-8-sig'))
    h = {'Content-Type': 'application/json', 'Authorization': 'Basic ' + base64.b64encode(f"{creds['user']}:{creds['password']}".encode()).decode()}
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}/index.php?rest_route=/{trasa}', data=json.dumps(dane).encode() if dane is not None else None, headers=h, method=metoda)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except ValueError:
            return e.code, None


def _stan(sciezka):
    try:
        return json.loads(pathlib.Path(sciezka).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'dodane_wydarzenia': [], 'dodane_druzyny': [], 'kosz': [], 'flagi': []}


def _zapisz(sciezka, stan):
    p = pathlib.Path(sciezka)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(stan, ensure_ascii=False, indent=1), encoding='utf-8')


def zakonczone_dywizji_a(api):
    """Rozegrane mecze Dywizji A (liga nalf-l19, sezon nalf-s61): [{id, teams, results, title, date}] od najstarszego."""
    k, l = api('GET', 'sportspress/v2/leagues&slug=nalf-l19&_fields=id')
    k2, s = api('GET', 'sportspress/v2/seasons&slug=nalf-s61&_fields=id')
    if k != 200 or k2 != 200 or not l or not s:
        raise SystemExit('Nie znaleziono Dywizji A (nalf-l19) albo sezonu (nalf-s61) w tej bazie.')
    k, ev = api('GET', f'sportspress/v2/events&leagues={l[0]["id"]}&seasons={s[0]["id"]}&per_page=100&orderby=id&order=asc&_fields=id,teams,results,main_results,title,date,leagues,seasons')
    zak = [e for e in ev if e.get('main_results')]
    if len(zak) < 4:
        raise SystemExit(f'Za mało rozegranych meczów Dywizji A w tej bazie ({len(zak)}).')
    return l[0]['id'], s[0]['id'], zak


def nazwa(api, e):
    k, t = api('GET', f'sportspress/v2/teams&include={",".join(str(x) for x in e["teams"])}&_fields=id,title&per_page=10')
    n = {x['id']: x['title']['rendered'] for x in t}
    return ' - '.join(n.get(x, '?') for x in e['teams'])


def wykonaj(akcja, api=api_8099, sciezka_stanu=STAN, wypisz=print):
    stan = _stan(sciezka_stanu)
    if akcja == 'cofnij':
        for eid in stan['dodane_wydarzenia']:
            api('DELETE', f'sportspress/v2/events/{eid}&force=true')
        for tid in stan['dodane_druzyny']:
            api('DELETE', f'sportspress/v2/teams/{tid}&force=true')
        for eid in stan['kosz']:
            api('POST', f'sportspress/v2/events/{eid}', {'status': 'publish'})
        for eid in stan['flagi']:
            api('POST', f'sportspress/v2/events/{eid}', {'meta': {'bm_zrodlo_brak': False}})
        wypisz(f'Cofnięto: usunięto {len(stan["dodane_wydarzenia"])} wydarzeń i {len(stan["dodane_druzyny"])} drużyn, przywrócono z kosza {len(stan["kosz"])}, zdjęto flagi {len(stan["flagi"])}.')
        try:
            pathlib.Path(sciezka_stanu).unlink()
        except OSError:
            pass
        return stan
    liga, sezon, zak = zakonczone_dywizji_a(api)
    akcje = ['duplikat', 'obca', 'flaga', 'kosz'] if akcja == 'wszystko' else [akcja]
    if any(a not in ('duplikat', 'obca', 'flaga', 'kosz') for a in akcje):
        raise SystemExit('Akcja: duplikat | obca | flaga | kosz | wszystko | cofnij')
    for a in akcje:
        if a == 'duplikat':
            e = zak[0]
            wyniki = {str(t): {'goals': str(r.get('goals')), 'outcome': list(r.get('outcome') or [])} for t, r in (e['results'] or {}).items() if str(t) in {str(x) for x in e['teams']}}
            k, n = api('POST', 'sportspress/v2/events', {'title': 'Duplikat (próba)', 'status': 'publish', 'date': e['date'], 'teams': e['teams'], 'format': 'league',
                                                         'leagues': [liga], 'seasons': [sezon], 'results': wyniki})
            stan['dodane_wydarzenia'].append(n['id'])
            wypisz(f'DUPLIKAT: drugi wpis meczu {nazwa(api, e)} (wynik {"-".join(e["main_results"])}), id {n["id"]}')
        elif a == 'obca':
            k, t = api('POST', 'sportspress/v2/teams', {'title': 'Zzz Obca (próba)', 'status': 'publish'})
            stan['dodane_druzyny'].append(t['id'])
            gosp = zak[1]['teams'][0]
            k, n = api('POST', 'sportspress/v2/events', {'title': 'Obca (próba)', 'status': 'publish', 'date': '2026-11-06T12:00:00', 'teams': [gosp, t['id']], 'format': 'league',
                                                         'leagues': [liga], 'seasons': [sezon],
                                                         'results': {str(gosp): {'goals': '3', 'outcome': ['win']}, str(t['id']): {'goals': '1', 'outcome': ['loss']}}})
            stan['dodane_wydarzenia'].append(n['id'])
            wypisz(f'DRUŻYNA SPOZA LIGI: mecz drużyny z Dywizji A (id {gosp}) z „Zzz Obca (próba)” 3:1, id {n["id"]}')
        elif a == 'flaga':
            e = zak[2]
            api('POST', f'sportspress/v2/events/{e["id"]}', {'meta': {'bm_zrodlo_brak': True}})
            stan['flagi'].append(e['id'])
            wypisz(f'FLAGA bm_zrodlo_brak (zniknął ze źródła) na zakończonym meczu {nazwa(api, e)}, id {e["id"]}: zostaje w tabeli z ostrzeżeniem')
        elif a == 'kosz':
            e = zak[3]
            api('DELETE', f'sportspress/v2/events/{e["id"]}')
            stan['kosz'].append(e['id'])
            wypisz(f'KOSZ: mecz {nazwa(api, e)} (wynik {"-".join(e["main_results"])}), id {e["id"]}, przeniesiony do kosza: nie liczy się do tabeli')
    _zapisz(sciezka_stanu, stan)
    return stan


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    wykonaj(sys.argv[1])
