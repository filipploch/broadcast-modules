"""W8b: trasa bm/v1/table (tabela wirtualna na żądanie) wtyczki bm-pomocnik na PRAWDZIWYM WP (instancja testowa 8099, kopia bazy p8091; patrz wp_instancja.py).

Etap 1: reguły jawnego stanu (b), tryby final/live, baza bez zmian, błędy. Etap 2: ostrzeżenia spójności (d). Etap 5: złote wzorce z oczekiwaną tabelą.
Uruchomienie: python tests/modules/dry_run_w8b_wp.py   (wymaga wolnego portu 8099; kod wyjścia 0 = wszystko zaliczone)"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding='utf-8')
from wp_instancja import Instancja, Liga, oczekiwana_tabela  # noqa: E402

wyniki = []


def typ_ostrz(o, t):
    return [w for w in o['warnings'] if w['typ'] == t]



def sprawdz(opis, warunek, szczegol=''):
    wyniki.append((opis, bool(warunek)))
    print(('OK   ' if warunek else 'BŁĄD ') + opis + ((' | ' + str(szczegol)[:600]) if (not warunek and szczegol != '') else ''))


def porownaj(opis, liga, mode, kolejnosc_stat):
    """Tabela z WP kontra niezależne wyliczenie (kolejność i statystyki)."""
    k, o = liga.tabela(mode)
    kol, st, poz, remis = kolejnosc_stat
    uczestnicy = {x for m in liga.mecze for x in (m['h'], m['g']) if x is not None}      # tabela ma tylko drużyny, które mają jakikolwiek mecz w lidze
    kol = [i for i in kol if i in uczestnicy]
    if k != 200:
        sprawdz(opis, False, (k, o))
        return o
    ids = [r['team_id'] for r in o['rows']]
    oczek = [liga.druzyny[i] for i in kol]
    statystyki_ok = len(o['rows']) == len(kol) and all(all(r[c] == st[kol[n]][c] for c in ('p', 'w', 'd', 'l', 'f', 'a', 'gd', 'pts')) for n, r in enumerate(o['rows']))
    # pozycje i flagi pełnego remisu: oracle liczy je dla wszystkich drużyn, tabela ma tylko uczestników; numeracja 1,2,2,4 liczona od wierszy tabeli
    pozycje_oczek = []
    for n, i in enumerate(kol):
        pozycje_oczek.append(pozycje_oczek[n - 1] if n and poz[i] == poz[kol[n - 1]] else n + 1)
    pozycje_ok = [r['pos'] for r in o['rows']] == pozycje_oczek
    remis_ok = {r['team_id'] for r in o['rows'] if r['pelny_remis']} == {liga.druzyny[i] for i in remis if i in uczestnicy} and o['needs_draw'] == bool(remis & uczestnicy)
    sprawdz(opis, ids == oczek and statystyki_ok and pozycje_ok and remis_ok,
            ([r['name'] for r in o['rows']], [liga.NAZWY[i] for i in kol], [(r['name'], r['pos'], r['pts'], r['gd'], r['pelny_remis']) for r in o['rows']], pozycje_oczek))
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
    sprawdz('remis w punktach rozstrzygnięty kryterium a: pozycje są kolejnymi numerami (bez wspólnej), brak flagi pełnego remisu', [r['pos'] for r in o['rows']] == list(range(1, len(o['rows']) + 1))
            and not any(r['pelny_remis'] for r in o['rows']) and o['needs_draw'] is False and not typ_ostrz(o, 'pelny_remis'), [(r['name'], r['pos']) for r in o['rows']])

    # ---- kryteria b, c, d po kolei i pełny remis (regulamin 5.11; pozycja wspólna TYLKO przy pełnym remisie a-d)
    def mini_liga(nazwa, mecze, n=3):
        K = Liga(wp, n=n, nazwa=nazwa)
        for h, g, w in mecze:
            K.dodaj(h, g, w, stan='zakonczony')
        k, t = K.tabela('final')
        return K, t, [(r['name'], r['pos']) for r in t['rows']]
    # b: po 3 pkt z meczów bezpośrednich (A wygrało 1:0, B 2:0); różnica w meczach bezpośrednich: B +1, A -1
    K, t, wiersze = mini_liga('kb', [(0, 1, (1, 0)), (1, 0, (2, 0))])
    sprawdz('kryterium b: równe punkty i bilans bezpośredni, decyduje różnica bramek w meczach bezpośrednich (B przed A), pozycje 1 i 2', wiersze == [('Bbb', 1), ('Aaa', 2)] and not t['needs_draw'], wiersze)
    # c: mecz bezpośredni remis, A i B po 4 pkt, różnica bramek ogółem A +3, B +1
    K, t, wiersze = mini_liga('kc', [(0, 1, (1, 1)), (0, 2, (3, 0)), (1, 2, (1, 0))])
    sprawdz('kryterium c: remis bezpośredni, decyduje różnica bramek ogółem (A przed B), pozycje 1 i 2', wiersze[:2] == [('Aaa', 1), ('Bbb', 2)] and not t['needs_draw'], wiersze)
    # d: mecz bezpośredni remis, różnica ogółem równa (+1), A strzeliło 3, B 2
    K, t, wiersze = mini_liga('kd', [(0, 1, (1, 1)), (0, 2, (2, 1)), (1, 2, (1, 0))])
    sprawdz('kryterium d: równa różnica bramek ogółem, decyduje większa liczba strzelonych bramek (A przed B), pozycje 1 i 2', wiersze[:2] == [('Aaa', 1), ('Bbb', 2)] and not t['needs_draw'], wiersze)
    # pełny remis: A-B 0:0, C-D 2:0 i 0:2 (rewanż): A i B po 1 pkt, C i D po 3 pkt, wszystkie kryteria a-d równe w obu parach
    K, t, wiersze = mini_liga('kpr', [(0, 1, (0, 0)), (2, 3, (2, 0)), (3, 2, (2, 0))], n=4)
    sprawdz('pełny remis a-d (równe punkty, bilans bezpośredni, różnica i bramki): wspólne pozycje 1,1,3,3 i flaga „wymaga losowania”', [r['pos'] for r in t['rows']] == [1, 1, 3, 3] and t['needs_draw'] is True
            and all(r['pelny_remis'] for r in t['rows']) and len(typ_ostrz(t, 'pelny_remis')) == 2, [(r['name'], r['pos'], r['pelny_remis']) for r in t['rows']])
    sprawdz('ostrzeżenie o pełnym remisie wymienia drużyny, „wymaga losowania” i wspólną pozycję', 'losowania' in typ_ostrz(t, 'pelny_remis')[0]['opis'] and 'Ccc' in typ_ostrz(t, 'pelny_remis')[0]['opis']
            and typ_ostrz(t, 'pelny_remis')[0]['wplyw'] == 'wspólna pozycja 1', typ_ostrz(t, 'pelny_remis'))
    sprawdz('odpowiedź opisuje przyjęte czytanie niejasnych zapisów jako wariant do potwierdzenia', 'do potwierdzenia' in t['interpretacja']['wariant'] and 'różnica bramek (nie iloraz)' in t['interpretacja']['b_stosunek']
            and 'jeden przebieg' in t['interpretacja']['mala_tabela_5_12'], t['interpretacja'])
    # drużyny bez żadnego meczu (początek sezonu): wspólna pozycja, ale bez flagi losowania
    K, t, wiersze = mini_liga('kzero', [], n=3)
    sprawdz('liga bez rozegranych meczów: wspólna pozycja 1 dla wszystkich, ale bez flagi „wymaga losowania”', [r['pos'] for r in t['rows']] == [1, 1, 1] and t['needs_draw'] is False and not typ_ostrz(t, 'pelny_remis'),
            [(r['name'], r['pos']) for r in t['rows']])

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
            pozycje = [r['pos'] for r in o['rows']]
            sprawdz(f'{wz["nazwa"]} [{tryb}]: kolejność, pozycje, statystyki i ostrzeżenia zgodne ze wzorcem',
                    k == 200 and kolejnosc == oczek['kolejnosc'] and tabela == oczek['tabela'] and ostrz == sorted(oczek['ostrzezenia'])
                    and pozycje == oczek.get('pozycje', list(range(1, len(kolejnosc) + 1))), (k, kolejnosc, pozycje, tabela, ostrz))

    # złoty wzorzec NALF ze stanu 5.11.2026 (WAŻNY TYLKO DLA TEGO STANU): mecze z API organizatora + tabele organizatora; tabela final z kodu kontra kolumna „wg regulaminu”
    import html
    nalf = json.loads((katalog / 'nalf_2026-11-05.json').read_text(encoding='utf-8'))
    for dyw, dane in nalf['dywizje'].items():
        druzyny = sorted({m['gospodarz'] for m in dane['mecze']} | {m['gosc'] for m in dane['mecze']})

        class LigaNalf(Liga):
            NAZWY = druzyny
        N = LigaNalf(wp, n=len(druzyny), nazwa='nalf' + dyw[-1].lower())
        idx = {nazwa: i for i, nazwa in enumerate(druzyny)}
        for m in dane['mecze']:
            N.dodaj(idx[m['gospodarz']], idx[m['gosc']], tuple(m['wynik']), stan='zakonczony', data=m['data'] + 'T12:00:00')
        k, t = N.tabela('final')
        wiersze = [(html.unescape(r['name']), r['p'], r['w'], r['d'], r['l'], r['f'], r['a'], r['pts'], r['pos']) for r in t['rows']] if k == 200 else []
        oczek = [(w['druzyna'], w['m'], w['z'], w['r'], w['p'], w['gz'], w['gs'], w['pkt'], w['poz_regulamin']) for w in dane['tabela']]
        sprawdz(f'Złoty wzorzec NALF 5.11.2026, {dyw}: kolejność, statystyki (M, Z, R, P, GZ, GS, Pkt) i pozycje wg regulaminu zgodne z kodem', k == 200 and wiersze == oczek
                and not any(r['pelny_remis'] for r in t['rows']) and t['needs_draw'] is False, [(a, b) for a, b in zip(wiersze, oczek) if a != b][:4] or (k, len(wiersze), len(oczek)))
        poz_strony = {w['druzyna']: w['poz_strona'] for w in dane['tabela']}
        roznice = sorted(n for (n, *_, poz) in wiersze if poz != poz_strony[n])
        sprawdz(f'Złoty wzorzec NALF 5.11.2026, {dyw}: jedyna różnica względem pozycji na stronie organizatora to ' + ('Drink Team (wg regulaminu 3, na stronie 2)' if dyw.endswith('B') else 'brak różnic'),
                roznice == (['Drink Team'] if dyw.endswith('B') else []), roznice)

    # przypadki brzegowe z próby ręcznej na prawdziwych danych kopii (Dywizja A): duplikat, drużyna spoza ligi, flaga, kosz, a potem cofnięcie (proba_tabela_przygotuj.py)
    import tempfile
    import proba_tabela_przygotuj as pp
    k, l = wp.api('GET', 'sportspress/v2/leagues&slug=nalf-l19&_fields=id')
    k, sz = wp.api('GET', 'sportspress/v2/seasons&slug=nalf-s61&_fields=id')
    kdyw = f'bm/v1/table&league={l[0]["id"]}&season={sz[0]["id"]}&mode=final'
    k, przed = wp.api('GET', kdyw)
    stan_pliku = pathlib.Path(tempfile.mkdtemp(prefix='bm-proba-tabela-')) / 'stan.json'
    sprawdz('kopia: Dywizja A przed przypadkami brzegowymi nie ma ostrzeżeń', k == 200 and przed['warnings'] == [] and przed['matches_counted'] > 0, (k, przed.get('warnings')))
    pp.wykonaj('wszystko', api=wp.api, sciezka_stanu=stan_pliku, wypisz=lambda *a: None)
    k, po = wp.api('GET', kdyw)
    typy = sorted({w['typ'] for w in po['warnings']})
    sprawdz('przypadki brzegowe na danych kopii: dokładnie 3 ostrzeżenia (duplikat, drużyna spoza ligi, zniknięcie ze źródła)', typy == ['druzyna_spoza_ligi', 'duplikat_meczu', 'zniknal_ze_zrodla'] and len(po['warnings']) == 3, [(w['typ'], w['mecz']) for w in po['warnings']])
    sprawdz('liczba meczów w tabeli: +1 duplikat, +1 mecz z obcą drużyną, −1 mecz w koszu; mecz z flagą zostaje', po['matches_counted'] == przed['matches_counted'] + 1, (przed['matches_counted'], po['matches_counted']))
    sprawdz('mecz z drużyną spoza ligi nie dodaje wiersza obcej drużyny do tabeli', all('Obca' not in r['name'] for r in po['rows']) and len(po['rows']) == len(przed['rows']), [r['name'] for r in po['rows']])
    pp.wykonaj('cofnij', api=wp.api, sciezka_stanu=stan_pliku, wypisz=lambda *a: None)
    k, wroc = wp.api('GET', kdyw)
    sprawdz('cofnięcie przywraca tabelę i ostrzeżenia sprzed przypadków brzegowych', [(r['name'], r['pos'], r['p'], r['pts'], r['gd']) for r in wroc['rows']] == [(r['name'], r['pos'], r['p'], r['pts'], r['gd']) for r in przed['rows']]
            and wroc['warnings'] == [] and wroc['matches_counted'] == przed['matches_counted'], (wroc['matches_counted'], wroc['warnings']))

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
