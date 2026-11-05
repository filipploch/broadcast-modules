"""W8b: trasa bm/v1/table (tabela wirtualna na żądanie) wtyczki bm-pomocnik na PRAWDZIWYM WP (instancja testowa 8099, kopia bazy p8091; patrz wp_instancja.py).

Etap 1: reguły jawnego stanu (b), tryby final/live, baza bez zmian, błędy. Etap 2: ostrzeżenia spójności (d). Etap 5: złote wzorce z oczekiwaną tabelą.
Uruchomienie: python tests/modules/dry_run_w8b_wp.py   (wymaga wolnego portu 8099; kod wyjścia 0 = wszystko zaliczone)"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding='utf-8')
from wp_instancja import Instancja, Liga, oczekiwana_tabela  # noqa: E402

wyniki = []


def sprawdz(opis, warunek, szczegol=''):
    wyniki.append((opis, bool(warunek)))
    print(('OK   ' if warunek else 'BŁĄD ') + opis + ((' | ' + str(szczegol)[:600]) if (not warunek and szczegol != '') else ''))


def porownaj(opis, liga, mode, kolejnosc_stat):
    """Tabela z WP kontra niezależne wyliczenie (kolejność i statystyki)."""
    k, o = liga.tabela(mode)
    kol, st = kolejnosc_stat
    if k != 200:
        sprawdz(opis, False, (k, o))
        return o
    ids = [r['team_id'] for r in o['rows']]
    oczek = [liga.druzyny[i] for i in kol]
    statystyki_ok = all(all(r[c] == st[kol[n]][c] for c in ('p', 'w', 'd', 'l', 'f', 'a', 'gd', 'pts')) for n, r in enumerate(o['rows']))
    sprawdz(opis, ids == oczek and statystyki_ok and [r['pos'] for r in o['rows']] == list(range(1, len(kol) + 1)),
            ([r['name'] for r in o['rows']], [liga.NAZWY[i] for i in kol], [(r['name'], r['pts'], r['gd']) for r in o['rows']]))
    return o


with Instancja() as wp:
    # ---- etap 1: reguły (b)
    L = Liga(wp, nazwa='e1')
    # kolejka zakończonych: A-B 2:0, C-D 1:1, E-F 3:1, A-C 0:0, B-E 2:2, D-F 1:0
    L.dodaj(0, 1, (2, 0), stan='zakonczony')
    L.dodaj(2, 3, (1, 1), stan='zakonczony')
    L.dodaj(4, 5, (3, 1))                      # bez bm_state: stan niejawny = zakończony (jak mecze z pełnego importu)
    L.dodaj(0, 2, (0, 0), stan='zakonczony')
    L.dodaj(1, 4, (2, 2), stan='zakonczony')
    L.dodaj(3, 5, (1, 0), stan='zakonczony')
    o = porownaj('final: sama liczba zakończonych, kolejność i statystyki jak niezależne wyliczenie', L, 'final', oczekiwana_tabela(L.mecze, 'final'))
    sprawdz('odpowiedź: pola, kolumny z etykietami, silnik SAH2H i kryteria t1-nalf', o.get('mode') == 'final' and o.get('engine') == 'SAH2H' and o.get('criteria') == 't1-nalf'
            and [c['klucz'] for c in o['columns']] == ['p', 'w', 'd', 'l', 'f', 'a', 'gd', 'pts', 'wa'] and [c['etykieta'] for c in o['columns']] == ['M', 'W', 'R', 'P', 'BZ', 'BS', 'RB', 'Pkt', 'WyW']
            and o['matches_counted'] == 6 and o['live_matches'] == 0 and o.get('computed_at') and all(k in o['rows'][0] for k in ('name14', 'short', 'team_id', 'pos')), o)

    # nierozpoczęty z wynikiem resztkowym: nigdy
    L.dodaj(1, 3, (5, 0), stan='nierozpoczety')
    porownaj('nierozpoczęty z resztkowym wynikiem natywnym nie liczy się (final)', L, 'final', oczekiwana_tabela(L.mecze, 'final'))
    porownaj('nierozpoczęty z resztkowym wynikiem natywnym nie liczy się (live)', L, 'live', oczekiwana_tabela(L.mecze, 'live'))
    # trwa bez wyniku na żywo: ani final, ani live
    L.dodaj(5, 0, None, stan='trwa')
    # trwa z wynikiem na żywo: tylko live
    L.dodaj(2, 5, None, stan='trwa', na_zywo='3:0')
    # trwa z wynikiem na żywo, ale z flagą: wyłączony z live
    L.dodaj(3, 4, None, stan='trwa', na_zywo='4:0', flaga=True)
    # zakończony z flagą zostaje
    L.dodaj(4, 0, (1, 0), stan='zakonczony', flaga=True)
    # nierozpoczęty z flagą i bez wyniku: nic
    L.dodaj(1, 2, None, stan='nierozpoczety', flaga=True)
    o_final = porownaj('final: trwające (z wynikiem na żywo, bez, z flagą) nie liczą się, zakończony z flagą zostaje', L, 'final', oczekiwana_tabela(L.mecze, 'final'))
    o_live = porownaj('live: dodaje tylko trwający z wynikiem na żywo bez flagi; bez wyniku na żywo i z flagą pominięte', L, 'live', oczekiwana_tabela(L.mecze, 'live'))
    sprawdz('live: liczba meczów live = 1, liczone = zakończone + 1', o_live['live_matches'] == 1 and o_live['matches_counted'] == o_final['matches_counted'] + 1, (o_live['live_matches'], o_live['matches_counted'], o_final['matches_counted']))

    # baza bez zmian: wynik na żywo nie trafia do sp_results, tabela nie tworzy wpisów
    ev_live = next(m['id'] for m in L.mecze if m['na_zywo'] == '3:0')
    k, e = wp.api('GET', f'sportspress/v2/events/{ev_live}&_fields=id,main_results,results,meta')
    sprawdz('baza bez zmian po trybie live: mecz trwający nadal bez wyniku natywnego, wynik na żywo w polu własnym', not e['main_results'] and e['meta'].get('bm_live_score') == '3:0', e)
    k, tab = wp.api('GET', 'sportspress/v2/tables&_fields=id')
    sprawdz('baza bez zmian: tabela nie tworzy wpisu sp_table', k == 200 and tab == [], (k, tab))
    k, o2 = L.tabela('live')
    sprawdz('idempotencja: drugie wywołanie live daje te same wiersze', [(r['team_id'], r['pts']) for r in o2['rows']] == [(r['team_id'], r['pts']) for r in o_live['rows']])
    k, o3 = L.tabela('final')
    sprawdz('po trybie live tryb final nie zawiera nakładki (te same wiersze co wcześniej)', [(r['team_id'], r['pts']) for r in o3['rows']] == [(r['team_id'], r['pts']) for r in o_final['rows']])

    # mecz kończy się: z live przechodzi do final
    wp.api('POST', f'bm/v1/event/{ev_live}/state', {'seq': 1, 'state': 'zakonczony', 'home': 3, 'away': 0})
    L.mecze[[m['id'] for m in L.mecze].index(ev_live)].update(wynik=(3, 0), stan='zakonczony')
    porownaj('po zakończeniu meczu przez moduł tabela final uwzględnia go', L, 'final', oczekiwana_tabela(L.mecze, 'final'))

    # ---- kolejność: remis w punktach rozstrzygają bezpośrednie spotkania PRZED różnicą bramek ogółem
    H = Liga(wp, nazwa='h2h')
    # A i B po 6 punktów; B pokonał A 1:0 (bezpośredni), ale A ma dużo lepszą różnicę bramek ogółem (+10 wobec +2)
    H.dodaj(1, 0, (1, 0), stan='zakonczony')      # B-A 1:0
    H.dodaj(0, 2, (6, 0), stan='zakonczony')      # A-C 6:0
    H.dodaj(0, 3, (5, 0), stan='zakonczony')      # A-D 5:0
    H.dodaj(1, 4, (1, 0), stan='zakonczony')      # B-E 1:0
    o = porownaj('remis w punktach: bezpośrednie spotkania przed różnicą bramek ogółem (zgodnie z regulaminem NALF)', H, 'final', oczekiwana_tabela(H.mecze, 'final'))
    nazwy = [r['name'] for r in o['rows']]
    sprawdz('przykład: B przed A mimo gorszej różnicy bramek (kolejność niezależnego wyliczenia = tabela WP)', nazwy.index('Bbb') < nazwy.index('Aaa') if 'Bbb' in nazwy and 'Aaa' in nazwy else False, nazwy)
    sprawdz('pozycja = numer wiersza także przy remisie punktowym (SAH2H daje wspólną pozycję, pomijamy ją)', [r['pos'] for r in o['rows']] == list(range(1, len(o['rows']) + 1)))

    # ---- błędy
    k, o = wp.api('GET', f'bm/v1/table&league={L.liga}&season={L.sezon}&mode=zly')
    sprawdz('zły tryb: 400', k == 400, (k, o))
    k, o = wp.api('GET', 'bm/v1/table&mode=final')
    sprawdz('brak ligi i sezonu: 400', k == 400, (k, o))
    k, o = wp.api('GET', 'bm/v1/table&league=999999&season=999998&mode=final')
    sprawdz('nieznana liga: 404 (bm_no_table)', k == 404 and o.get('code') == 'bm_no_table', (k, o))
    puste = Liga(wp, n=0, nazwa='puste')
    k, o = puste.tabela('final')
    sprawdz('liga bez drużyn (np. puchar): 404 „brak tabeli”', k == 404 and o.get('code') == 'bm_no_table', (k, o))
    k, o = L.tabela('final', criteria='nie-ma-takich')
    sprawdz('nieznane kryteria: tabela zwykła SportsPressa i ostrzeżenie o konfiguracji', k == 200 and o['engine'] == 'SP' and any(w['typ'] == 'konfiguracja' for w in o['warnings']), (k, o.get('engine')))
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:8099/index.php?rest_route=/bm/v1/table&league={L.liga}&season={L.sezon}'), timeout=20)
        anon = 200
    except Exception as e:
        anon = getattr(e, 'code', 0)
    sprawdz('bez logowania: 401/403 (trasa wymaga uprawnień edycji)', anon in (401, 403), anon)

zle = [o for o, ok in wyniki if not ok]
print(f'\nWYNIK: {"WSZYSTKO ZALICZONE" if not zle else "NIEZALICZONE: " + str(len(zle))} ({len(wyniki)} sprawdzeń)')
sys.exit(1 if zle else 0)
