"""W8a-0/W8a: trasa bm/v1/event/<id>/state wtyczki bm-pomocnik na PRAWDZIWYM WP (testy PHP zastąpione wywołaniami REST z Pythona, decyzja z planu W8a).

Uruchamia własną, jednorazową instancję WP na porcie 8099 (kod wp-local/wordpress, baza = kopia bazy p8091 w wp-local/databases/p8099, dane logowania z dane-api-nalf.json,
które dotyczą tej kopii), tworzy własne mecze testowe przez REST SportsPressa i sprawdza zachowanie trasy. Po próbie zatrzymuje TYLKO swój proces (po numerze PID)
i usuwa bazę p8099. Nie dotyka baz p8091/p8092 ani folderu transmisyjnego. Wymaga wolnego portu 8099."""
import base64
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
REPO = pathlib.Path(__file__).resolve().parents[2]
WPL = REPO / 'wp-local'
PORT = 8099
BASE = f'http://127.0.0.1:{PORT}/index.php?rest_route=/'
DB_DIR = WPL / 'databases' / f'p{PORT}'
creds = json.loads((WPL / 'dane-api-nalf.json').read_text(encoding='utf-8-sig'))
TOKEN = base64.b64encode(f"{creds['user']}:{creds['password']}".encode()).decode()

wyniki = []


def sprawdz(opis, warunek, szczegol=''):
    wyniki.append((opis, bool(warunek)))
    print(('OK   ' if warunek else 'BŁĄD ') + opis + ((' | ' + str(szczegol)) if (not warunek and szczegol != '') else ''))


def api(metoda, trasa, dane=None, auth=True, timeout=60):
    ciało = json.dumps(dane).encode() if dane is not None else None
    h = {'Content-Type': 'application/json'}
    if auth:
        h['Authorization'] = 'Basic ' + TOKEN
    req = urllib.request.Request(BASE + trasa, data=ciało, headers=h, method=metoda)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except ValueError:
            return e.code, None


def stan(eid, seq, state, home=None, away=None):
    return api('POST', f'bm/v1/event/{eid}/state', {'seq': seq, 'state': state, 'home': home, 'away': away})


def mecz(eid):
    return api('GET', f'sportspress/v2/events/{eid}&_fields=id,status,main_results,results,teams,meta')[1]


port_zajety = False
try:
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/', timeout=2):
        port_zajety = True
except Exception:
    pass
if port_zajety:
    sys.exit(f'Port {PORT} jest zajęty; zamknij to, co go używa.')

if DB_DIR.exists():
    shutil.rmtree(DB_DIR)
DB_DIR.mkdir(parents=True)
for nazwa in ('.ht.sqlite', '.htaccess'):
    zrodlo = WPL / 'databases' / 'p8091' / nazwa
    if zrodlo.exists():
        shutil.copy2(zrodlo, DB_DIR / nazwa)

proc = subprocess.Popen([str(WPL / 'php' / 'php.exe'), 'wp-cli.phar', '--path=wordpress', 'server', '--host=127.0.0.1', f'--port={PORT}'], cwd=str(WPL),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
try:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/', timeout=5):
                break
        except Exception:
            time.sleep(1)
    else:
        sys.exit('WP testowy nie wystartował w 60 s')

    kod, druzyny = api('GET', 'sportspress/v2/teams&per_page=4&_fields=id')
    t1, t2 = druzyny[0]['id'], druzyny[1]['id']

    def nowy(status='future', teams=None, data='2030-01-01T12:00:00'):
        k, e = api('POST', 'sportspress/v2/events', {'title': 'Test W8a', 'status': status, 'date': data, 'teams': teams or [t1, t2]})
        assert k in (200, 201), (k, e)
        return e['id']

    # -- 1. stan „trwa” z wynikiem na żywo
    e = nowy()
    k, o = stan(e, 1, 'trwa', 0, 0)
    sprawdz('trwa: 200 i stan w odpowiedzi', k == 200 and o['state'] == 'trwa' and o['live_score'] == '0:0' and not o['duplicate'], (k, o))
    m = mecz(e)
    sprawdz('trwa: bm_live prawda, bm_state i wynik na żywo w polach meczu', m['meta'].get('bm_live') is True and m['meta'].get('bm_state') == 'trwa' and m['meta'].get('bm_live_score') == '0:0', m['meta'])
    sprawdz('trwa: natywnego wyniku nie ma, status bez zmian (future)', not m['main_results'] and m['status'] == 'future', (m['main_results'], m['status']))
    k, o = stan(e, 2, 'trwa', 2, 1)
    sprawdz('wynik na żywo się zmienia', k == 200 and mecz(e)['meta']['bm_live_score'] == '2:1')

    # -- 2. idempotencja
    k, o = stan(e, 2, 'trwa', 9, 9)
    sprawdz('powtórzone seq: potwierdzone bez zmian (duplicate)', k == 200 and o['duplicate'] and mecz(e)['meta']['bm_live_score'] == '2:1', (k, o))
    k, o = stan(e, 1, 'trwa', 7, 7)
    sprawdz('starsze seq: ignorowane', k == 200 and o['duplicate'] and mecz(e)['meta']['bm_live_score'] == '2:1')

    # -- 3. zakończenie: natywny wynik tylko tutaj
    k, o = stan(e, 3, 'zakonczony', 3, 1)
    m = mecz(e)
    sprawdz('zakonczony: wynik natywny 3:1, bm_live fałsz, brak wyniku na żywo (mecz z datą w przyszłości zostaje „future”: WordPress tak ustawia status)',
            k == 200 and m['main_results'] == ['3', '1'] and m['meta'].get('bm_live') is False and not m['meta'].get('bm_live_score') and m['status'] == 'future', (k, m))
    r = m['results']
    sprawdz('zakonczony: wyniki drużyn i rezultaty (win/loss)', r[str(t1)]['goals'] == '3' and r[str(t1)]['outcome'] == ['win'] and r[str(t2)]['outcome'] == ['loss'], r)
    sprawdz('zakonczony: źródło wyniku = moduł', m['meta'].get('bm_result_source') == 'modul' and m['meta'].get('bm_state') == 'zakonczony')

    # -- 4. poprawka wyniku przez moduł (WP nie zmieniono)
    k, o = stan(e, 4, 'zakonczony', 3, 3)
    m = mecz(e)
    sprawdz('poprawka po zakończeniu przez moduł (remis): wynik 3:3, rezultat draw', k == 200 and m['main_results'] == ['3', '3'] and m['results'][str(t1)]['outcome'] == ['draw'], (k, m['main_results']))

    # -- 5. organizator zmienia wynik w WP: moduł nie nadpisuje
    api('POST', f'sportspress/v2/events/{e}', {'results': {str(t1): {'goals': '5', 'outcome': ['win']}, str(t2): {'goals': '0', 'outcome': ['loss']}}})
    k, o = stan(e, 5, 'zakonczony', 3, 3)
    sprawdz('wynik zmieniony przez organizatora: moduł dostaje 409 bm_wp_result z wynikiem WP', k == 409 and o.get('code') == 'bm_wp_result' and o['data'].get('wp_result') == [5, 0], (k, o))
    sprawdz('wynik organizatora zostaje', mecz(e)['main_results'] == ['5', '0'])
    k, o = stan(e, 6, 'zakonczony', 5, 0)
    sprawdz('ten sam wynik co w WP: przyjęty bez zmiany', k == 200 and mecz(e)['main_results'] == ['5', '0'])
    k, o = stan(e, 7, 'nierozpoczety')
    sprawdz('cofnięcie do „nierozpoczęty” meczu z wynikiem organizatora: 409', k == 409 and mecz(e)['main_results'] == ['5', '0'], (k, o))
    k, o = stan(e, 8, 'trwa', 1, 1)
    sprawdz('„trwa” dla meczu z wynikiem organizatora: 409', k == 409)

    # -- 6. blokada
    e2 = nowy()
    api('POST', f'sportspress/v2/events/{e2}', {'meta': {'bm_locked': True}})
    k, o = stan(e2, 1, 'trwa', 0, 0)
    sprawdz('bm_locked: 409 bm_locked', k == 409 and o.get('code') == 'bm_locked', (k, o))

    # -- 7. cofnięcie wyniku wpisanego przez moduł
    e3 = nowy()
    stan(e3, 1, 'zakonczony', 2, 0)
    k, o = stan(e3, 2, 'nierozpoczety')
    m = mecz(e3)
    sprawdz('cofnięcie meczu zakończonego przez moduł: wynik usunięty, stan nierozpoczęty', k == 200 and not m['main_results'] and m['meta'].get('bm_state') == 'nierozpoczety' and not m['meta'].get('bm_result_source'), (k, m))

    # -- 8. walidacja
    e4 = nowy()
    sprawdz('zły stan: 400', stan(e4, 1, 'dziwny')[0] == 400)
    sprawdz('brak seq: 400', api('POST', f'bm/v1/event/{e4}/state', {'state': 'trwa'})[0] == 400)
    sprawdz('zakończony bez wyniku: 400', stan(e4, 1, 'zakonczony')[0] == 400)
    sprawdz('wynik ujemny: 400', stan(e4, 1, 'trwa', -1, 0)[0] == 400)
    sprawdz('to nie jest mecz: 404', api('POST', f'bm/v1/event/{t1}/state', {'seq': 1, 'state': 'trwa'})[0] == 404)
    e5 = nowy(teams=[0, 0])
    k, o = stan(e5, 1, 'trwa', 0, 0)
    sprawdz('mecz bez ustalonych drużyn („Do ustalenia”): 409 bm_no_teams', k == 409 and o.get('code') == 'bm_no_teams', (k, o))
    sprawdz('bez logowania: 401/403', api('POST', f'bm/v1/event/{e4}/state', {'seq': 1, 'state': 'trwa'}, auth=False)[0] in (401, 403))

    # -- 9. mecz w przeszłości dostaje status publish po zakończeniu
    e6 = nowy(status='publish', data='2026-09-01T12:00:00')
    stan(e6, 1, 'zakonczony', 1, 0)
    sprawdz('mecz z datą w przeszłości po zakończeniu: publish i wynik 1:0', mecz(e6)['status'] == 'publish' and mecz(e6)['main_results'] == ['1', '0'])

    # -- 10. natywne wyniki nie powstają przed zakończeniem (tabela SportsPressa ich nie zlicza)
    e7 = nowy()
    stan(e7, 1, 'trwa', 4, 4)
    sprawdz('„trwa”: natywny wynik nadal pusty', not mecz(e7)['main_results'])

    # -- 11. klient modułu (WpClient.post_json) rozmawia z prawdziwą trasą: JSON z null, konflikt 409 jako WpError('conflict')
    sys.path[:0] = [str(REPO / 'modules')]
    from core.managers.wp_client import WpClient, WpConfig, WpError
    klient = WpClient(WpConfig(enabled=True, url=f'http://127.0.0.1:{PORT}', user=creds['user'], password=creds['password']), timeout=20)
    e8 = nowy()
    odp = klient.post_json(f'bm/v1/event/{e8}/state', {'state': 'nierozpoczety', 'home': None, 'away': None, 'seq': 1})
    sprawdz('klient modułu: nierozpoczęty z null w wyniku przyjęty', odp.get('ok') is True and odp.get('state') == 'nierozpoczety', odp)
    odp = klient.post_json(f'bm/v1/event/{e8}/state', {'state': 'trwa', 'home': 1, 'away': 0, 'seq': 2})
    sprawdz('klient modułu: trwa 1:0', odp.get('live_score') == '1:0', odp)
    api('POST', f'sportspress/v2/events/{e8}', {'meta': {'bm_locked': True}})
    try:
        klient.post_json(f'bm/v1/event/{e8}/state', {'state': 'trwa', 'home': 2, 'away': 0, 'seq': 3})
        sprawdz('klient modułu: blokada zgłasza WpError(conflict)', False)
    except WpError as err:
        sprawdz('klient modułu: blokada zgłasza WpError(conflict) z kodem bm_locked', err.kind == 'conflict' and err.code == 'bm_locked' and 'zablokowany' in str(err), (err.kind, err.code, str(err)))

    # -- 12. rzuty karne i zwycięzca (W8a): zwycięzca z wyniku, a przy remisie z konkursu; pola tylko przy „zakonczony”
    def stan_k(eid, seq, state, home=None, away=None, ph=None, pa=None):
        return api('POST', f'bm/v1/event/{eid}/state', {'seq': seq, 'state': state, 'home': home, 'away': away, 'pen_home': ph, 'pen_away': pa})
    e9 = nowy()
    k, o = stan_k(e9, 1, 'zakonczony', 2, 1)
    m = mecz(e9)['meta']
    sprawdz('zwycięzca z wyniku: bm_winner = home, drużyna gospodarzy, bez konkursu', k == 200 and m.get('bm_winner') == 'home' and m.get('bm_winner_team') == t1 and not m.get('bm_pen_home'), (k, m))
    k, o = stan_k(e9, 2, 'zakonczony', 2, 2, 4, 5)
    m = mecz(e9)['meta']
    sprawdz('remis i konkurs 4:5: zwycięzca = away (drużyna gości), pola konkursu zapisane', k == 200 and m.get('bm_winner') == 'away' and m.get('bm_winner_team') == t2
            and m.get('bm_pen_home') == 4 and m.get('bm_pen_away') == 5, (k, m))
    sprawdz('odpowiedź zawiera zwycięzcę i konkurs', o.get('winner') == 'away' and o.get('winner_team') == t2 and o.get('pen') == [4, 5], o)
    k, o = stan_k(e9, 3, 'zakonczony', 1, 1)
    m = mecz(e9)['meta']
    sprawdz('remis bez konkursu: brak zwycięzcy i pól konkursu', k == 200 and m.get('bm_winner') == '' and not m.get('bm_winner_team') and not m.get('bm_pen_home') and o.get('pen') == [None, None], (k, m, o))
    k, o = stan_k(e9, 4, 'zakonczony', 1, 1, 3, 3)
    sprawdz('remis w konkursie (3:3) nie wyłania zwycięzcy', k == 200 and mecz(e9)['meta'].get('bm_winner') == '', (k, mecz(e9)['meta']))
    k, o = stan_k(e9, 5, 'zakonczony', 1, 1, 3, None)
    sprawdz('konkurs z jedną wartością: 400', k == 400 and o.get('code') == 'bm_bad_pen', (k, o))
    k, o = stan_k(e9, 6, 'zakonczony', 1, 1, -1, 2)
    sprawdz('konkurs z wartością ujemną: 400', k == 400, k)
    stan_k(e9, 7, 'zakonczony', 0, 0, 2, 4)
    k, o = stan(e9, 8, 'trwa', 1, 0)
    m = mecz(e9)['meta']
    sprawdz('cofnięcie do „trwa” kasuje zwycięzcę i konkurs', k == 200 and not m.get('bm_winner') and not m.get('bm_winner_team') and not m.get('bm_pen_home'), (k, m))
    e10 = nowy()
    stan_k(e10, 1, 'zakonczony', 0, 0, 5, 3)
    k, o = stan(e10, 2, 'nierozpoczety')
    m = mecz(e10)['meta']
    sprawdz('cofnięcie do „nierozpoczęty” kasuje zwycięzcę i konkurs', k == 200 and not m.get('bm_winner') and not m.get('bm_pen_home'), (k, m))
    # zwycięzca zostaje po poprawce wyniku organizatora tylko, gdy moduł zapisze ten sam wynik (WP jest właścicielem wyniku)
    e11 = nowy()
    stan_k(e11, 1, 'zakonczony', 1, 1, 4, 2)
    api('POST', f'sportspress/v2/events/{e11}', {'results': {str(t1): {'goals': '3', 'outcome': ['win']}, str(t2): {'goals': '0', 'outcome': ['loss']}}})
    k, o = stan_k(e11, 2, 'zakonczony', 1, 1, 4, 2)
    sprawdz('wynik zmieniony przez organizatora: zapis konkursu z modułu nadal 409 (reguła zamknięcia bez zmian)', k == 409 and o.get('code') == 'bm_wp_result', (k, o))

    # -- 13. pierwszeństwo danych: flaga bm_decyduje (ustawiana polem „decyduje” trasy stanu) i trasa stanu ze źródła (import)
    def zrodlo(eid, state, home=None, away=None):
        return api('POST', f'bm/v1/event/{eid}/source-state', {'state': state, 'home': home, 'away': away})
    e12 = nowy()
    k, o = api('POST', f'bm/v1/event/{e12}/state', {'seq': 1, 'state': 'nierozpoczety', 'decyduje': True})
    sprawdz('flaga decyduje ustawiona razem ze stanem; odpowiedź ją zawiera', k == 200 and o.get('decyduje') is True and mecz(e12)['meta'].get('bm_decyduje'), (k, o))
    k, o = stan(e12, 2, 'trwa', 1, 0)
    sprawdz('zapis stanu bez pola „decyduje” nie rusza flagi', k == 200 and o.get('decyduje') is True, (k, o))
    k, o = zrodlo(e12, 'trwa', 3, 3)
    sprawdz('stan ze źródła dla meczu z flagą decyduje: 409, stan i wynik na żywo bez zmian', k == 409 and o.get('code') == 'bm_decyduje'
            and mecz(e12)['meta'].get('bm_live_score') == '1:0', (k, o, mecz(e12)['meta']))
    k, o = api('POST', f'bm/v1/event/{e12}/state', {'seq': 3, 'state': 'trwa', 'home': 1, 'away': 0, 'decyduje': False})
    sprawdz('flaga zdjęta polem decyduje=false', k == 200 and o.get('decyduje') is False and not mecz(e12)['meta'].get('bm_decyduje'), (k, o))
    e13 = nowy()
    stan(e13, 1, 'nierozpoczety')
    seq_przed = mecz(e13)['meta'].get('bm_seq')
    k, o = zrodlo(e13, 'trwa', 2, 1)
    m = mecz(e13)['meta']
    sprawdz('stan ze źródła: trwa 2:1 zapisany (bm_state, bm_live_score, bm_live), bm_seq bez zmian', k == 200 and m.get('bm_state') == 'trwa'
            and m.get('bm_live_score') == '2:1' and m.get('bm_live') and m.get('bm_seq') == seq_przed, (k, m))
    k, o = zrodlo(e13, 'trwa', 2, 2)
    sprawdz('kolejny stan ze źródła nadpisuje wynik na żywo', k == 200 and mecz(e13)['meta'].get('bm_live_score') == '2:2', (k, o))
    k, o = zrodlo(e13, 'zakonczony', 2, 2)
    m = mecz(e13)['meta']
    sprawdz('stan ze źródła „zakonczony”: bm_state zakonczony, wynik na żywo skasowany, natywny wynik nietknięty', k == 200 and m.get('bm_state') == 'zakonczony'
            and not m.get('bm_live_score') and not m.get('bm_live') and not mecz(e13).get('main_results'), (k, m))
    k, o = zrodlo(e13, 'cos')
    sprawdz('źródło z nieznanym stanem: 400', k == 400, (k, o))
    e14 = nowy()
    api('POST', f'sportspress/v2/events/{e14}', {'meta': {'bm_locked': True}})
    k, o = zrodlo(e14, 'trwa', 1, 0)
    sprawdz('stan ze źródła dla meczu z bm_locked: 409', k == 409, (k, o))
    k, o = stan(e14, 1, 'trwa', 1, 0)
    sprawdz('bm_locked nadal blokuje zapis z modułu (409 bm_locked): flaga decyduje to osobne pole', k == 409 and o.get('code') == 'bm_locked', (k, o))

    # -- 14. natywny wynik istnieje tylko dla meczów zakończonych; flaga bm_zrodlo_brak
    e15 = nowy()
    stan(e15, 1, 'zakonczony', 3, 1)
    sprawdz('mecz zakończony przez moduł ma natywny wynik 3:1', mecz(e15).get('main_results') == ['3', '1'], mecz(e15).get('main_results'))
    k, o = stan(e15, 2, 'trwa', 0, 0)
    m = mecz(e15)
    sprawdz('powrót do „trwa” z modułu czyści natywny wynik i jego ślad', k == 200 and not m.get('main_results') and not m['meta'].get('bm_result_source'), (k, m))
    e16 = nowy()
    api('POST', f'sportspress/v2/events/{e16}', {'results': {str(t1): {'goals': '2', 'outcome': ['win']}, str(t2): {'goals': '0', 'outcome': ['loss']}}})
    sprawdz('wynik wpisany w WP (jak z importu) jest natywnym wynikiem', mecz(e16).get('main_results') == ['2', '0'], mecz(e16).get('main_results'))
    k, o = zrodlo(e16, 'trwa', 0, 0)
    m = mecz(e16)
    sprawdz('stan „trwa” ze źródła czyści natywny wynik (także cudzy) i ustawia wynik na żywo', k == 200 and not m.get('main_results') and m['meta'].get('bm_live_score') == '0:0', (k, m))
    e17 = nowy()
    api('POST', f'sportspress/v2/events/{e17}', {'results': {str(t1): {'goals': '1', 'outcome': ['win']}, str(t2): {'goals': '0', 'outcome': ['loss']}}})
    k, o = zrodlo(e17, 'nierozpoczety')
    m = mecz(e17)
    sprawdz('stan „nierozpoczety” ze źródła czyści natywny wynik, bm_state nierozpoczety', k == 200 and not m.get('main_results') and m['meta'].get('bm_state') == 'nierozpoczety', (k, m))
    e18 = nowy()
    api('POST', f'sportspress/v2/events/{e18}', {'meta': {'bm_decyduje': True}})
    k, o = zrodlo(e18, 'nierozpoczety')
    sprawdz('stan „nierozpoczety” ze źródła dla meczu z flagą decyduje: 409', k == 409, (k, o))
    api('POST', f'sportspress/v2/events/{e17}', {'meta': {'bm_zrodlo_brak': True}})
    sprawdz('flaga bm_zrodlo_brak zapisuje się przez REST i nie usuwa meczu', mecz(e17)['meta'].get('bm_zrodlo_brak') is True and mecz(e17).get('id') == e17, mecz(e17)['meta'])
finally:
    pid = proc.pid
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)
    time.sleep(1)
    shutil.rmtree(DB_DIR, ignore_errors=True)

zle = [o for o, ok in wyniki if not ok]
print(f'\nWYNIK: {"WSZYSTKO ZALICZONE" if not zle else "NIEZALICZONE: " + str(len(zle))} ({len(wyniki)} sprawdzeń)')
sys.exit(1 if zle else 0)
