"""Import danych ze stron do WP/SportsPressa instancji modułu (I1: NALF, I2: Garbarnia z Superscore).

    python tools/import_wp/importuj.py nalf|garbarnia [--sezon <id>] [--na-sucho] [--bez-zawodnikow] [--cache <katalog>]

Wymaga uruchomionej instancji WP modułu (wp-nalf.bat) i pliku wp-local\\dane-api-<id>.json. Odczyt ze strony z przerwą 1 s między zapytaniami.
Import jest powtarzalny: drugie uruchomienie niczego nie dubluje (dopasowanie po bm_source_id), a rekordy bez zmian nie są wysyłane.
--na-sucho: tylko raport (co byłoby dodane i zmienione), bez zapisu do WP."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nalf as zrodlo_nalf  # noqa: E402
import superscore as zrodlo_superscore  # noqa: E402
from upsert import Import  # noqa: E402
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
        payload = {k: t[k] for k in ('name', 'slug', 'abbreviation')} | {'leagues': [l for l in t['leagues'] if l in dane['ligi']]}
        imp.upsert('druzyny', TRASY['druzyny'], t['id'], payload, lambda t=t: {
            'title': t['name'], **({'slug': t['slug']} if t['slug'] else {}), 'status': 'publish', 'abbreviation': t['abbreviation'],
            'leagues': _ids(payload['leagues'], wp_ligi), 'seasons': [wp_sezon]})
    imp.raportuj_brakujace('druzyny', [t['id'] for t in dane['druzyny']])

    if z_zawodnikami:
        for p in dane['zawodnicy']:
            payload = {'name': p['name'], 'slug': p['slug'], 'number': p['number'], 'teams': p['teams'],
                       'leagues': [l for l in p['leagues'] if l in dane['ligi']]}
            imp.upsert('zawodnicy', TRASY['zawodnicy'], p['id'], payload, lambda p=p, payload=payload: {
                'title': p['name'], **({'slug': p['slug']} if p['slug'] else {}), 'status': 'publish', **({'number': p['number']} if p['number'] is not None else {}),
                'teams': _ids(p['teams'], imp.id_wp['druzyny']), 'leagues': _ids(payload['leagues'], wp_ligi), 'seasons': [wp_sezon]})
        imp.raportuj_brakujace('zawodnicy', [p['id'] for p in dane['zawodnicy']])
        imp.wykryj_duplikaty_zawodnikow(dane['zawodnicy'])

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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('zrodlo', choices=sorted(ZRODLA))
    ap.add_argument('--sezon', help='id sezonu w źródle (domyślnie z zrodla.json)')
    ap.add_argument('--na-sucho', action='store_true')
    ap.add_argument('--bez-zawodnikow', action='store_true')
    ap.add_argument('--cache', help='katalog pamięci podręcznej odpowiedzi źródła (do prac deweloperskich; domyślnie wyłączona)')
    a = ap.parse_args(argv)
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
    print(raport(imp, a.na_sucho))
    print(f'  zapytań do WP: {wp.zapytania}')
    return 1 if any(l.bledy for l in imp.liczniki.values()) else 0


if __name__ == '__main__':
    sys.exit(main())
