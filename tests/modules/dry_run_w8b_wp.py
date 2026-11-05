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

    # ---- etap 2: ostrzeżenia spójności (d); nie blokują, tabela zawsze się liczy
    W = Liga(wp, nazwa='ostrz')
    W.dodaj(0, 1, (2, 0), stan='zakonczony')                         # zwykły mecz
    id_dup1 = W.dodaj(2, 3, (1, 0), stan='zakonczony')               # duplikat: ta sama para dwa razy, oba z wynikiem
    id_dup2 = W.dodaj(2, 3, (1, 0), stan='zakonczony')
    id_dup_pusty = W.dodaj(4, 5, None, stan='nierozpoczety')         # duplikat zapowiedzi (bez wyniku): liczy się 0 razy
    W.dodaj(4, 5, None, stan='nierozpoczety')
    k, obcy = wp.api('POST', 'sportspress/v2/teams', {'title': 'Zzz Obca', 'status': 'publish'})   # drużyna bez ligi i sezonu
    id_obcy = W.dodaj(None, None, (3, 1), stan='zakonczony', druzyny=[W.druzyny[4], obcy['id']])
    id_resz_n = W.dodaj(1, 2, (4, 0), stan='nierozpoczety')          # resztkowy wynik w nierozpoczętym
    id_resz_t = W.dodaj(3, 4, (2, 0), stan='trwa', na_zywo='1:0')    # resztkowy wynik natywny w trwającym (z wynikiem na żywo)
    id_bez_w = W.dodaj(5, 0, None, stan='zakonczony')                # zakończony bez wyniku
    id_bez_zywo = W.dodaj(5, 1, None, stan='trwa')                   # trwa bez wyniku na żywo
    id_znik_z = W.dodaj(0, 3, (1, 1), stan='zakonczony', flaga=True) # zniknął ze źródła, zakończony: zostaje
    id_znik_t = W.dodaj(2, 4, None, stan='trwa', na_zywo='2:2', flaga=True)   # zniknął ze źródła, trwa: wyłączony z live

    def typ(o, t, mecz=None):
        return [w for w in o['warnings'] if w['typ'] == t and (mecz is None or w['mecz_id'] == mecz)]
    k, fo = W.tabela('final')
    k, lv = W.tabela('live')
    sprawdz('ostrzeżenia nie blokują: tabela jest policzona w obu trybach', k == 200 and len(fo['rows']) == 6 and len(lv['rows']) == 6, (k, fo.get('rows') and len(fo['rows'])))
    sprawdz('ostrzeżenie: duplikat meczu (para liczona dwa razy)', len(typ(fo, 'duplikat_meczu', id_dup1)) == 1 and 'liczona wielokrotnie (2 razy)' in typ(fo, 'duplikat_meczu', id_dup1)[0]['wplyw'], typ(fo, 'duplikat_meczu'))
    sprawdz('duplikat zapowiedzi bez wyników: ostrzeżenie z wpływem „liczony 0 raz”', len(typ(fo, 'duplikat_meczu', id_dup_pusty)) == 1 and 'liczony 0 raz' in typ(fo, 'duplikat_meczu', id_dup_pusty)[0]['wplyw'], typ(fo, 'duplikat_meczu'))
    sprawdz('ostrzeżenie: drużyna spoza ligi', len(typ(fo, 'druzyna_spoza_ligi', id_obcy)) == 1 and 'Zzz Obca' in typ(fo, 'druzyna_spoza_ligi', id_obcy)[0]['opis'], typ(fo, 'druzyna_spoza_ligi'))
    sprawdz('ostrzeżenie: resztkowy wynik w meczu nierozpoczętym (wynik pominięty)', len(typ(fo, 'wynik_resztkowy', id_resz_n)) == 1 and typ(fo, 'wynik_resztkowy', id_resz_n)[0]['wplyw'] == 'wynik pominięty', typ(fo, 'wynik_resztkowy'))
    sprawdz('ostrzeżenie: resztkowy wynik natywny w meczu trwającym', len(typ(fo, 'wynik_resztkowy', id_resz_t)) == 1)
    sprawdz('ostrzeżenie: zakończony bez wyniku', len(typ(fo, 'zakonczony_bez_wyniku', id_bez_w)) == 1 and typ(fo, 'zakonczony_bez_wyniku', id_bez_w)[0]['wplyw'] == 'nie liczy się do tabeli')
    sprawdz('trwa bez wyniku na żywo: ostrzeżenie tylko w trybie live', len(typ(lv, 'trwa_bez_wyniku_na_zywo', id_bez_zywo)) == 1 and typ(fo, 'trwa_bez_wyniku_na_zywo') == [], (typ(lv, 'trwa_bez_wyniku_na_zywo'), typ(fo, 'trwa_bez_wyniku_na_zywo')))
    sprawdz('ostrzeżenie: zniknął ze źródła, zakończony zostaje w tabeli (final i live)', len(typ(fo, 'zniknal_ze_zrodla', id_znik_z)) == 1 and typ(fo, 'zniknal_ze_zrodla', id_znik_z)[0]['wplyw'] == 'zostaje w tabeli' and len(typ(lv, 'zniknal_ze_zrodla', id_znik_z)) == 1)
    sprawdz('ostrzeżenie: zniknął ze źródła, trwający wyłączony z tabeli live (w final bez ostrzeżenia)', len(typ(lv, 'zniknal_ze_zrodla', id_znik_t)) == 1 and 'wyłączony' in typ(lv, 'zniknal_ze_zrodla', id_znik_t)[0]['wplyw'] and typ(fo, 'zniknal_ze_zrodla', id_znik_t) == [])
    sprawdz('pola ostrzeżenia: typ, mecz_id, mecz (nazwa), opis, wplyw', all(set(w) == {'typ', 'mecz_id', 'mecz', 'opis', 'wplyw'} for w in fo['warnings']) and all(w['mecz'] for w in fo['warnings'] if w['typ'] != 'konfiguracja'))
    sprawdz('mecz bez żadnego problemu nie ma ostrzeżeń', not [w for w in fo['warnings'] if w['mecz_id'] == W.mecze[0]['id']])
    g = Liga(wp, nazwa='czysta')
    g.dodaj(0, 1, (1, 0), stan='zakonczony')
    k, cz = g.tabela('live')
    sprawdz('czysta liga: pusta lista ostrzeżeń', k == 200 and cz['warnings'] == [], cz.get('warnings'))

    # ---- etap 5: złote wzorce (tests/modules/zlote_wzorce/z*.json): ręcznie policzona tabela oczekiwana dla final i live + lista ostrzeżeń
    import json
    katalog = pathlib.Path(__file__).resolve().parent / 'zlote_wzorce'
    for plik in sorted(katalog.glob('z*.json')):
        wz = json.loads(plik.read_text(encoding='utf-8'))
        G = Liga(wp, n=len(wz['druzyny']), nazwa=plik.stem[:2])
        G.NAZWY = wz['druzyny']
        for m in wz['mecze']:
            G.dodaj(m['h'], m['g'], tuple(m['wynik']) if m.get('wynik') else None, stan=m.get('stan'), na_zywo=m.get('na_zywo'), flaga=m.get('flaga', False))
        for tryb in ('final', 'live'):
            k, o = G.tabela(tryb)
            oczek = wz[tryb]
            nazwy_wp = {G.druzyny[i]: wz['druzyny'][i] for i in range(len(wz['druzyny']))}
            kolejnosc = [nazwy_wp[r['team_id']] for r in o['rows']]
            tabela = {nazwy_wp[r['team_id']]: {'p': r['p'], 'pts': r['pts'], 'gd': r['gd']} for r in o['rows']}
            ostrz = sorted(w['typ'] for w in o['warnings'] if w['typ'] != 'konfiguracja')
            sprawdz(f'{wz["nazwa"]} [{tryb}]: kolejność, statystyki i ostrzeżenia zgodne ze wzorcem',
                    k == 200 and kolejnosc == oczek['kolejnosc'] and tabela == oczek['tabela'] and ostrz == sorted(oczek['ostrzezenia']), (k, kolejnosc, tabela, ostrz))

    # porównanie z tabelą organizatora NALF (fixtura dostarczona przez właściciela; pusta = pominięte)
    org = json.loads((katalog / 'organizator_nalf_dywizja_a.json').read_text(encoding='utf-8'))
    if org.get('wiersze'):
        k, l = wp.api('GET', f'sportspress/v2/leagues&slug={org["liga_slug"]}&_fields=id')
        k2, sz = wp.api('GET', f'sportspress/v2/seasons&slug={org["sezon_slug"]}&_fields=id')
        k3, t = wp.api('GET', f'bm/v1/table&league={l[0]["id"]}&season={sz[0]["id"]}&mode=final')
        mapa = [(r['pos'], r['name'], r['p'], r['w'], r['d'], r['l'], r['f'], r['a'], r['pts']) for r in t['rows']]
        wzor = [(w['poz'], w['druzyna'], w['m'], w['w'], w['r'], w['p'], w['bz'], w['bs'], w['pkt']) for w in org['wiersze']]
        sprawdz(f'tabela final z WP zgodna z tabelą organizatora NALF (stan na {org.get("stan_na", "?")})', mapa[:len(wzor)] == wzor, [(a, b) for a, b in zip(mapa, wzor) if a != b][:5])
    else:
        print('POMINIĘTO porównanie z tabelą organizatora NALF: brak fixtury (tests/modules/zlote_wzorce/organizator_nalf_dywizja_a.json, wiersze puste)')

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
