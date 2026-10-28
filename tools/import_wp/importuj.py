"""Import danych ze stron do WP/SportsPressa instancji modułu (I1: NALF, I2: Garbarnia z Superscore).

    python tools/import_wp/importuj.py nalf|garbarnia [--sezon <id>] [--na-sucho] [--bez-zawodnikow] [--cache <katalog>]

Wymaga uruchomionej instancji WP modułu (wp-nalf.bat) i pliku wp-local\\dane-api-<id>.json. Odczyt ze strony z przerwą 1 s między zapytaniami.
Import jest powtarzalny: drugie uruchomienie niczego nie dubluje (dopasowanie po bm_source_id), a rekordy bez zmian nie są wysyłane.
--na-sucho: tylko raport (co byłoby dodane i zmienione), bez zapisu do WP."""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nalf as zrodlo_nalf  # noqa: E402
import superscore as zrodlo_superscore  # noqa: E402
from upsert import Import, nazwa_do_porownania  # noqa: E402
from wp_rest import WpRest, WpRestError, wczytaj_dane_logowania  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ZRODLA = json.loads((Path(__file__).resolve().parent / 'zrodla.json').read_text(encoding='utf-8'))
TRASY = {'druzyny': 'sportspress/v2/teams', 'zawodnicy': 'sportspress/v2/players', 'mecze': 'sportspress/v2/events'}


def wp_dir():
    return Path(os.environ.get('BM_WP_DIR') or REPO / 'wp-local')


def polacz_z_wp(modul_folder):
    """Instancja WP modułu: adres z bloku wp w module.json, logowanie z wp-local\\dane-api-<id>.json."""
    mj = json.loads((REPO / 'modules' / modul_folder / 'module.json').read_text(encoding='utf-8-sig'))
    blok = mj.get('wp')
    if not isinstance(blok, dict):
        raise SystemExit(f'Moduł {modul_folder} nie ma bloku wp w module.json.')
    user, haslo = wczytaj_dane_logowania(wp_dir(), mj['id'])
    return WpRest(f'http://127.0.0.1:{int(blok["port"])}', user, haslo), int(blok['port']), mj['id']


def _ids(lista, mapa):
    return [mapa[i] for i in lista if i in mapa]


def _klasyfikuj_przynaleznosc(imp, p, nazwy):
    """Zlicza zawodnika do jednej z grup: jedna aktualna drużyna sezonu / kilka aktualnych (lista z nazwami) / tylko dawne / źródło bez pól."""
    k = imp.przynaleznosc
    if p.get('current_teams') is None:
        k['brak_pol'] += 1
        return
    aktualne = [t for t in p['current_teams'] if t in nazwy]
    if len(aktualne) > 1:
        k['kilka'].append(f'{p["name"]}: ' + ', '.join(nazwy[t] for t in aktualne))
    elif not aktualne:
        k['tylko_dawne'].append(f'{p["name"]}: dawne ' + (', '.join(nazwy[t] for t in (p.get('past_teams') or []) if t in nazwy) or 'brak'))
    else:
        k['jedna'] += 1


PROG_ZNIKANIA = 0.25            # ponad tyle składu znikającego naraz (i co najmniej MIN_ZNIKAJACYCH osób) = podejrzenie awarii źródła
MIN_ZNIKAJACYCH = 5


def _opuscili_sklad(imp, wp, dane, zrodlo, na_sucho):
    """Superscore: zawodnik, którego nie ma już w składach źródła, przechodzi z current_teams do past_teams (rekord nigdy nie jest usuwany).
    Bezpieczniki: drużyna z pustym/niepobranym składem jest pomijana; gdy z jednej drużyny znika naraz ponad 25% składu (min. 5 osób),
    przeniesień nie robimy, tylko je wypisujemy do decyzji. Stary rekord bez rozróżnienia (puste current/past) traktuje 'teams' jak aktualne."""
    imp.opuscili, imp.opuscili_do_decyzji = [], []
    if zrodlo != 'superscore':
        return
    w_zrodle = {str(p['id']) for p in dane['zawodnicy']}
    sklady = dane.get('sklady') or {}
    odwrot = {wp_id: src for src, wp_id in imp.id_wp['druzyny'].items() if wp_id}
    nazwy = {str(t['id']): t['name'] for t in dane['druzyny']}
    istn = imp.istniejace['zawodnicy']

    def aktualne(ist):
        return ist['cur'] if (ist['cur'] or ist['past']) else ist['teams']

    rozmiar = {}
    for ist in istn.values():
        for t in aktualne(ist):
            rozmiar[t] = rozmiar.get(t, 0) + 1
    kandydaci = {}
    for sid, ist in istn.items():
        if sid in w_zrodle:
            continue
        for t in aktualne(ist):
            if t in odwrot:
                kandydaci.setdefault(t, []).append((sid, ist))
    przenosimy = {}                                                         # sid -> (ist, zbiór drużyn WP do przeniesienia)
    for t, lista in sorted(kandydaci.items()):
        nazwa = nazwy.get(str(odwrot[t]), str(t))
        opis = ', '.join(nazwa_do_porownania_czytelna(ist) for _, ist in lista[:10])
        if not sklady.get(str(odwrot[t])) and not sklady.get(odwrot[t]):
            imp.opuscili_do_decyzji.append(f'{nazwa}: skład pobrany pusty albo niepełny, nie przenoszę {len(lista)} zawodników ({opis})')
            continue
        if len(lista) >= MIN_ZNIKAJACYCH and len(lista) / max(rozmiar.get(t, 1), 1) > PROG_ZNIKANIA:
            imp.opuscili_do_decyzji.append(f'{nazwa}: z {rozmiar.get(t, 0)} zawodników znika naraz {len(lista)} (ponad 25%), nie przenoszę, '
                                           f'do Twojej decyzji (możliwa awaria źródła): {opis}')
            continue
        for sid, ist in lista:
            przenosimy.setdefault(sid, (ist, set()))[1].add(t)
    licz = imp.liczniki['zawodnicy']
    for sid, (ist, druzyny_wp) in sorted(przenosimy.items(), key=lambda x: x[1][0]['id']):
        nowe_cur = [t for t in aktualne(ist) if t not in druzyny_wp]
        nowe_past = list(dict.fromkeys(ist['past'] + sorted(druzyny_wp)))
        nazwy_dr = ', '.join(nazwy.get(str(odwrot[t]), str(t)) for t in sorted(druzyny_wp))
        imp.opuscili.append(f'{nazwa_do_porownania_czytelna(ist)}: opuścił skład ({nazwy_dr}), przeniesiono do dawnych (id WP {ist["id"]})')
        if na_sucho:
            continue
        try:
            wp.zaktualizuj(TRASY['zawodnicy'], ist['id'], {'current_teams': nowe_cur, 'past_teams': nowe_past,
                                                         'teams': list(dict.fromkeys(nowe_cur + nowe_past))})
        except Exception as e:                                              # jeden zły rekord nie przerywa importu
            licz.bledy += 1
            licz.uwagi.append(f'zawodnicy {sid}: przeniesienie do dawnych: {e}')


def nazwa_do_porownania_czytelna(ist):
    return ist['nazwa'].title() if ist.get('nazwa') else f'id WP {ist["id"]}'


def importuj_zrodlo(wp, zrodlo, dane, z_zawodnikami=True, na_sucho=False, log=print):
    """Zapisuje do WP dane znormalizowane przez nalf.pobierz_sezon albo superscore.pobierz_sezon. Zwraca obiekt Import z licznikami."""
    imp = Import(wp, zrodlo, na_sucho=na_sucho, log=log)
    sezon = dane['sezon']
    wp_sezon = imp.kategorie('sezon', [sezon])[sezon['id']]
    wp_ligi = imp.kategorie('ligi', list(dane['ligi'].values()))
    for rodzaj in ('druzyny', 'zawodnicy', 'mecze'):
        imp.wczytaj_istniejace(rodzaj, TRASY[rodzaj])
    nazwy = {t['id']: t['name'] for t in dane['druzyny']}

    for t in dane['druzyny']:
        payload = {k: t[k] for k in ('name', 'slug', 'abbreviation')} | {'leagues': [l for l in t['leagues'] if l in dane['ligi']],
                                                                        'bm_short_name': t['abbreviation'][:3].upper()}
        ist_dr = imp.istniejace['druzyny'].get(str(t['id']))

        def body_druzyny(t=t, payload=payload, ist=ist_dr):
            cialo = {'title': t['name'], **({'slug': t['slug']} if t['slug'] else {}), 'status': 'publish', 'abbreviation': t['abbreviation'],
                     'leagues': _ids(payload['leagues'], wp_ligi), 'seasons': [wp_sezon]}
            # skrót z API (Superscore short_code) zapisujemy tylko wtedy, gdy rekord jeszcze nie ma bm_short_name (ręczna poprawka w WP zostaje)
            if payload['bm_short_name'] and (ist is None or not ist['skrot']):
                cialo['_meta'] = {'bm_short_name': payload['bm_short_name']}
            return cialo
        imp.upsert('druzyny', TRASY['druzyny'], t['id'], payload, body_druzyny)
    imp.raportuj_brakujace('druzyny', [t['id'] for t in dane['druzyny']])

    imp.przynaleznosc = {'jedna': 0, 'brak_pol': 0, 'kilka': [], 'tylko_dawne': []}      # klasyfikacja zawodników wg drużyn aktualnych (raport)
    if z_zawodnikami:
        for p in dane['zawodnicy']:
            _klasyfikuj_przynaleznosc(imp, p, nazwy)
            payload = {'name': p['name'], 'slug': p['slug'], 'number': p['number'], 'teams': p['teams'],
                       'current_teams': p.get('current_teams'), 'past_teams': p.get('past_teams'),
                       'leagues': [l for l in p['leagues'] if l in dane['ligi']], 'last_name': p['last_name'], 'first_name': p['first_name']}
            ist = imp.istniejace['zawodnicy'].get(str(p['id']))

            def body_zawodnika(p=p, payload=payload, ist=ist):
                cialo = {'title': p['name'], **({'slug': p['slug']} if p['slug'] else {}), 'status': 'publish',
                         **({'number': p['number']} if p['number'] is not None else {}),
                         'leagues': _ids(payload['leagues'], wp_ligi), 'seasons': [wp_sezon]}
                # drużyny aktualne i dawne osobno (SportsPress sam składa z nich 'teams'); źródło bez tych pól: tylko wspólna lista 'teams'
                if p.get('current_teams') is None:
                    cialo['teams'] = _ids(p['teams'], imp.id_wp['druzyny'])
                else:
                    cialo['current_teams'] = _ids(p['current_teams'], imp.id_wp['druzyny'])
                    cialo['past_teams'] = _ids(p.get('past_teams') or [], imp.id_wp['druzyny'])
                    # wspólną listę wysyłamy też: SportsPress NIE składa jej sam dla nowo utworzonych rekordów (potwierdzone na prawdziwym WP)
                    cialo['teams'] = list(dict.fromkeys(cialo['current_teams'] + cialo['past_teams']))
                # imię i nazwisko: zapis przy zakładaniu, przy zmianie nazwy w źródle albo gdy rekord jeszcze ich nie ma; w pozostałych
                # przypadkach zostaje wartość z WP (np. ręcznie poprawiona po raporcie „nazwiska niepewne”)
                if ist is None or not (ist['imie'] or ist['nazwisko']) or ist['nazwa'] != nazwa_do_porownania(p['name']):
                    cialo['_meta'] = {'bm_last_name': p['last_name'], 'bm_first_name': p['first_name']}
                return cialo
            # wspólna lista 'teams' w WP musi być sumą aktualnych i dawnych (SportsPress nie składa jej sam przy tworzeniu rekordu)
            niespojne = (ist is not None and p.get('current_teams') is not None and set(ist['teams']) != set(
                _ids(p['current_teams'], imp.id_wp['druzyny']) + _ids(p.get('past_teams') or [], imp.id_wp['druzyny'])))
            imp.upsert('zawodnicy', TRASY['zawodnicy'], p['id'], payload, body_zawodnika, wymus=niespojne)
            if p.get('name_uncertain'):
                zapisane = (ist['nazwisko'], ist['imie']) if ist and (ist['imie'] or ist['nazwisko']) else None
                if zapisane is None or zapisane == (p['last_name'], p['first_name']) or ist['nazwa'] != nazwa_do_porownania(p['name']):
                    imp.niepewne_nazwiska.append(f'{p["name"]}: nazwisko „{p["last_name"]}”, imię „{p["first_name"]}” (id WP {imp.id_wp["zawodnicy"].get(p["id"])})')
        imp.raportuj_brakujace('zawodnicy', [p['id'] for p in dane['zawodnicy']])
        imp.wykryj_duplikaty_zawodnikow(dane['zawodnicy'])
        _opuscili_sklad(imp, wp, dane, zrodlo, na_sucho)

    for m in dane['mecze']:
        if any(t and t not in imp.id_wp['druzyny'] for t in m['teams']):          # 0 = wolne miejsce w fazie pucharowej (para nieznana)
            licz = imp.liczniki['mecze']
            licz.bledy += 1
            licz.uwagi.append(f'mecz {m["id"]}: drużyna spoza pobranego sezonu')
            continue

        def body(m=m):
            gracze = imp.id_wp['zawodnicy']
            wyniki = {str(imp.id_wp['druzyny'][t]): v for t, v in m['results'].items() if t in imp.id_wp['druzyny']}
            body = {
                'title': ' - '.join(nazwy.get(t, 'Do ustalenia') for t in m['teams']), 'status': 'publish', 'date': m['date'], 'format': m['format'],
                'day': m['day'], 'leagues': _ids(m['leagues'], wp_ligi), 'seasons': [wp_sezon],
                'teams': [imp.id_wp['druzyny'][t] if t else 0 for t in m['teams']]}
            if m['minutes'].isdigit():
                body['minutes'] = int(m['minutes'])
            if wyniki:
                body['results'] = wyniki
            if z_zawodnikami and m['performance']:
                body['performance'] = {
                    str(imp.id_wp['druzyny'][t]): {str(gracze[p]): w for p, w in rows.items() if p in gracze}
                    for t, rows in m['performance'].items() if t in imp.id_wp['druzyny']}
                body['players'] = [gracze[p] if p else 0 for p in m['players'] if p == 0 or p in gracze]
            return body
        payload = {**m, 'z_zawodnikami': z_zawodnikami}
        payload.pop('status', None)                    # publish/future wynika z daty; nie ma wpływać na skrót
        imp.upsert('mecze', TRASY['mecze'], m['id'], payload, body,
                   przed_aktualizacja=lambda wp_id: wp.zadanie('POST', f'bm/v1/event/{wp_id}/clear'))
    imp.raportuj_brakujace('mecze', [m['id'] for m in dane['mecze']])
    imp.uwagi_zrodla = list(dane.get('uwagi') or [])
    return imp


def importuj_nalf(wp, dane, **kw):
    return importuj_zrodlo(wp, 'nalf', dane, **kw)


def raport(imp, na_sucho):
    nazwy = {'sezon': 'sezon', 'ligi': 'ligi', 'druzyny': 'drużyny', 'zawodnicy': 'zawodnicy', 'mecze': 'mecze'}
    wiersze = [('NA SUCHO: ' if na_sucho else '') + 'wynik importu']
    wiersze += [f'  uwaga źródła: {u}' for u in getattr(imp, 'uwagi_zrodla', [])]
    for k, n in nazwy.items():
        licz = imp.liczniki[k]
        wiersze.append(f'  {n:<10} {licz.linia()}')
    if getattr(imp, 'niepewne_nazwiska', None):
        wiersze.append(f'  NAZWISKA NIEPEWNE ({len(imp.niepewne_nazwiska)}): podział „Nazwisko Imię” zgadnięty (jedno słowo albo więcej niż dwa); '
                       f'popraw w WP w polach własnych bm_last_name i bm_first_name zawodnika, jeśli podział jest błędny (import ich potem nie nadpisze):')
        wiersze += [f'    - {n}' for n in imp.niepewne_nazwiska[:60]]
        if len(imp.niepewne_nazwiska) > 60:
            wiersze.append(f'    ... i {len(imp.niepewne_nazwiska) - 60} kolejnych')
    prz = getattr(imp, 'przynaleznosc', None)
    if prz:
        wiersze.append(f'  przynależność zawodników: {prz["jedna"]} z jedną aktualną drużyną, {len(prz["kilka"])} z kilkoma aktualnymi, '
                       f'{len(prz["tylko_dawne"])} tylko z dawnymi, {prz["brak_pol"]} ze źródła bez rozróżnienia (zostaje wspólna lista)')
        for tytul, klucz in (('KILKA AKTUALNYCH DRUŻYN', 'kilka'), ('TYLKO DAWNE DRUŻYNY w sezonie', 'tylko_dawne')):
            if prz[klucz]:
                wiersze.append(f'  {tytul} ({len(prz[klucz])}):')
                wiersze += [f'    - {n}' for n in prz[klucz][:40]]
                if len(prz[klucz]) > 40:
                    wiersze.append(f'    ... i {len(prz[klucz]) - 40} kolejnych')
    if getattr(imp, 'opuscili', None):
        wiersze.append(f'  OPUŚCILI SKŁAD W ŹRÓDLE ({len(imp.opuscili)}): ' + ('do przeniesienia' if na_sucho else 'przeniesieni') + ' z aktualnych do dawnych drużyn (rekordy zostają):')
        wiersze += [f'    - {n}' for n in imp.opuscili[:40]]
    if getattr(imp, 'opuscili_do_decyzji', None):
        wiersze.append(f'  DO DECYZJI ({len(imp.opuscili_do_decyzji)}): przeniesienia wstrzymane bezpiecznikiem:')
        wiersze += [f'    - {n}' for n in imp.opuscili_do_decyzji]
    for k, licz in imp.liczniki.items():
        if licz.nie_ma_w_zrodle:
            wiersze.append(f'  uwaga: w WP jest {len(licz.nie_ma_w_zrodle)} rekordów "{nazwy[k]}" z tego źródła, których nie ma w pobranym sezonie '
                           f'(mogą należeć do innych sezonów; nic nie usuwam)')
        for u in licz.uwagi[:10]:
            wiersze.append(f'  ! {u}')
        for d in licz.duplikaty[:20]:
            wiersze.append(f'  UWAGA, możliwy duplikat zawodnika: {d}')
        if len(licz.duplikaty) > 20:
            wiersze.append(f'  ... i {len(licz.duplikaty) - 20} kolejnych możliwych duplikatów')
    return '\n'.join(wiersze)


def ostrzezenie_cache(katalog):
    """Tekst ostrzeżenia o danych z pamięci podręcznej (z datą najstarszego zapisu) albo '' przy braku katalogu/plików."""
    pliki = [f for f in Path(katalog).glob('*.json') if f.is_file()] if katalog and Path(katalog).is_dir() else []
    if not pliki:
        return ''
    najstarszy = datetime.fromtimestamp(min(f.stat().st_mtime for f in pliki))
    return (f'UWAGA: DANE Z PAMIĘCI PODRĘCZNEJ ({katalog}), najstarszy zapis {najstarszy:%Y-%m-%d %H:%M}. '
            f'To nie jest stan źródła na żywo; nie używaj tego do prawdziwego importu.')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('zrodlo', choices=sorted(ZRODLA))
    ap.add_argument('--sezon', help='id sezonu w źródle (domyślnie z zrodla.json)')
    ap.add_argument('--na-sucho', action='store_true')
    ap.add_argument('--bez-zawodnikow', action='store_true')
    ap.add_argument('--cache', help='katalog pamięci podręcznej odpowiedzi źródła (do prac deweloperskich; domyślnie wyłączona: import czyta źródło na żywo)')
    ap.add_argument('--stare-dane-ok', action='store_true', help='pozwala na PRAWDZIWY import z danych pamięci podręcznej (domyślnie odrzucany)')
    a = ap.parse_args(argv)
    if a.cache and not a.na_sucho and not a.stare_dane_ok:
        sys.exit('Odmowa: --cache w prawdziwym imporcie czytałby stare dane zamiast stanu źródła na żywo (mogą cofnąć rekordy w WP). '
                 'Uruchom bez --cache albo dodaj --na-sucho; świadomie: --stare-dane-ok.')
    uwaga_cache = ostrzezenie_cache(a.cache) if a.cache else ''
    if uwaga_cache:
        print(uwaga_cache)
    konf = ZRODLA[a.zrodlo]
    wp, port, mod_id = polacz_z_wp(konf['modul'])
    api_zrodla = konf.get('zrodlo', a.zrodlo)
    print(f'Import {api_zrodla}, moduł {mod_id} -> WP (127.0.0.1:{port}){" [NA SUCHO]" if a.na_sucho else ""}')
    z_zaw = not a.bez_zawodnikow
    if api_zrodla == 'nalf':
        dane = zrodlo_nalf.pobierz_sezon(zrodlo_nalf.NalfApi(cache_dir=a.cache), int(a.sezon or konf['sezon']), z_zawodnikami=z_zaw)
        nazwa_zrodla = 'nalf'
    else:
        konf = {**konf, **({'sezon': a.sezon} if a.sezon else {})}
        dane = zrodlo_superscore.pobierz_sezon(zrodlo_superscore.SuperscoreApi(cache_dir=a.cache), konf, z_zawodnikami=z_zaw)
        nazwa_zrodla = 'superscore'
    print(f'  sezon: {dane["sezon"]["name"]}; ligi: ' + ', '.join(l['name'] for l in dane['ligi'].values()))
    try:
        imp = importuj_zrodlo(wp, nazwa_zrodla, dane, z_zawodnikami=z_zaw, na_sucho=a.na_sucho)
    except WpRestError as e:
        sys.exit(f'Błąd rozmowy z WP: {e}. Czy instancja działa (wp-nalf.bat albo wp-garbarnia.bat) i czy bm-pomocnik jest w mu-plugins?')
    if uwaga_cache:
        imp.uwagi_zrodla.insert(0, uwaga_cache)
    print(raport(imp, a.na_sucho))
    print(f'  zapytań do WP: {wp.zapytania}')
    return 1 if any(l.bledy for l in imp.liczniki.values()) else 0


if __name__ == '__main__':
    sys.exit(main())
