"""Lekki tryb „odśwież wyniki” (W8a): stan i wynik meczów jednej ligi i sezonu ze źródła do WP, bez zawodników, składów, logo i drużyn.

    python tools/import_wp/odswiez.py [nalf|garbarnia] [--na-sucho] [--liga <id źródła> --sezon <id źródła>]

Bez argumentów: moduł rozpoznawany po działającym module (adres zapisu do WP w /api/wp-zapis/status panelu 8081), a liga i sezon z bieżącego wyboru
rozgrywek modułu (modules/<moduł>/instance/wp_rozgrywki.json). Uruchamiane plikiem odswiez-wyniki.bat (dwuklik), bezpieczne w trakcie transmisji:
- zapisuje WYŁĄCZNIE wynik i stan meczów, które już są w WP (nie tworzy meczów, nie rusza składów ani statystyk, nie czyści wyniku przed zapisem),
- pomija mecz z flagą bm_decyduje (w tym mecz transmitowany) i bm_locked, tylko porównuje źródło z WP,
- Superscore: jedno zapytanie do źródła; NALF: wyniki meczów rozegranych (źródło nie ma wyniku na żywo),
- blokada pliku przed podwójnym uruchomieniem; na końcu podsumowanie."""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importuj  # noqa: E402
import nalf as zrodlo_nalf  # noqa: E402
import superscore as zrodlo_superscore  # noqa: E402
from upsert import Import, tekst_wp  # noqa: E402
from wp_rest import WpRestError  # noqa: E402

REPO = importuj.REPO
ZRODLA = importuj.ZRODLA
BLOKADA_WAZNA_S = 600                       # blokada starsza niż 10 minut to pozostałość po przerwanym uruchomieniu


class Zajete(Exception):
    pass


class Blokada:
    """Plik blokady (O_EXCL) w folderze wp-local: drugi dwuklik w trakcie odświeżania dostaje komunikat zamiast drugiego odświeżania."""

    def __init__(self, sciezka, teraz=time.time):
        self.sciezka = Path(sciezka)
        self.teraz = teraz

    def __enter__(self):
        self.sciezka.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(str(self.sciezka), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    wiek = self.teraz() - self.sciezka.stat().st_mtime
                except OSError:
                    continue
                if wiek < BLOKADA_WAZNA_S:
                    raise Zajete(f'Odświeżanie już trwa (zaczęte {int(wiek)} s temu). Poczekaj na jego koniec.')
                self.sciezka.unlink(missing_ok=True)       # przerwane uruchomienie: blokada przestarzała
                continue
            with os.fdopen(fd, 'w') as f:
                f.write(str(os.getpid()))
            return self
        raise Zajete('Nie udało się założyć blokady odświeżania.')

    def __exit__(self, *a):
        self.sciezka.unlink(missing_ok=True)


def moduly():
    """{id źródła w zrodla.json: (folder modułu, port WP modułu)}."""
    wynik = {}
    for klucz, konf in ZRODLA.items():
        mj = json.loads((REPO / 'modules' / konf['modul'] / 'module.json').read_text(encoding='utf-8-sig'))
        wynik[klucz] = (konf['modul'], int(mj['wp']['port']))
    return wynik


def rozpoznaj_modul(port_panelu=8081, otwarte=None):
    """Który moduł działa: z adresu zapisu do WP w statusie panelu; None, gdy się nie da (wtedy trzeba podać nazwę)."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port_panelu}/api/wp-zapis/status', timeout=3) as r:
            adres = (json.loads(r.read().decode()) or {}).get('adres') or ''
    except Exception:
        adres = ''
    m = re.search(r':(\d+)$', adres.rstrip('/'))
    if m:
        for klucz, (_, port) in moduly().items():
            if port == int(m.group(1)):
                return klucz
    return None


def wybor_rozgrywek(folder_modulu):
    """Liga i sezon w źródle z bieżącego wyboru rozgrywek modułu (slugi <źródło>-l<id> i <źródło>-s<id>) albo None."""
    sciezka = REPO / 'modules' / folder_modulu / 'instance' / 'wp_rozgrywki.json'
    try:
        d = (json.loads(sciezka.read_text(encoding='utf-8')) or {}).get('default')
    except (OSError, ValueError):
        return None
    if not d:
        return None
    ml = re.fullmatch(r'[a-z]+-l(.+)', d.get('league_slug') or '')
    ms = re.fullmatch(r'[a-z]+-s(.+)', d.get('season_slug') or '')
    if not ml or not ms:
        return None
    return {'liga': ml.group(1), 'sezon': ms.group(1), 'nazwa': f'{d.get("league_name", "")} — {d.get("season_name", "")}'}


def _zgodne(a, b):
    return str(a).lower() == str(b).lower()


def pobierz_ze_zrodla(klucz, liga, sezon, cache=None):
    """Mecze jednej ligi sezonu w formacie importera (bez zawodników). Zwraca (lista meczów, liczba zapytań)."""
    konf = ZRODLA[klucz]
    if konf.get('zrodlo', klucz) == 'nalf':
        api = zrodlo_nalf.NalfApi(cache_dir=cache)
        mecze = [zrodlo_nalf.norm_mecz(e) for e in api.get_all(
            'events', seasons=int(sezon), leagues=int(liga), _fields='id,date,status,format,day,minutes,leagues,seasons,teams,results')]
        return mecze, api.zapytania
    if not (_zgodne(konf['sezon'], sezon) and _zgodne(konf['liga']['id'], liga)):
        raise SystemExit(f'Bieżący wybór rozgrywek ({liga}/{sezon}) to nie liga i sezon ze źródła w zrodla.json ({konf["liga"]["id"]}/{konf["sezon"]}). '
                         f'Wybierz właściwe rozgrywki w module (Rozgrywki WP).')
    api = zrodlo_superscore.SuperscoreApi(cache_dir=cache)
    dane = zrodlo_superscore.pobierz_sezon(api, konf, z_zawodnikami=False, log=lambda *a: None)
    return [m for m in dane['mecze'] if liga.lower() in [str(l).lower() for l in m['leagues']]], api.zapytania


def _id_kategorii(wp, rodzaj, slug):
    trasa = 'sportspress/v2/' + ('leagues' if rodzaj == 'liga' else 'seasons')
    for t in wp.pobierz_wszystko(trasa, {'_fields': 'id,slug'}):
        if (t.get('slug') or '').lower() == slug.lower():
            return t['id']
    return None


def odswiez(wp, zrodlo, mecze, liga, sezon, na_sucho=False):
    """Zapisuje do WP stan i wynik meczów, które już w WP są. Zwraca słownik z podsumowaniem (zmienione, pominięte, bez zmian, brak w WP, błędy)."""
    imp = Import(wp, zrodlo, na_sucho=na_sucho, log=lambda *a: None)
    imp.stany_zywo = []
    id_liga = _id_kategorii(wp, 'liga', f'{zrodlo}-l{liga}')
    id_sezon = _id_kategorii(wp, 'sezon', f'{zrodlo}-s{sezon}')
    if not id_liga or not id_sezon:
        raise SystemExit(f'WP nie ma ligi albo sezonu z tego źródła ({zrodlo}-l{liga}, {zrodlo}-s{sezon}): najpierw pełny import (import-nalf.bat / import-garbarnia.bat).')
    istn_dr = imp.wczytaj_istniejace('druzyny', importuj.TRASY['druzyny'])
    nazwy_dr = {sid: ist['tytul'] for sid, ist in istn_dr.items()}
    for sid, ist in istn_dr.items():
        imp.id_wp['druzyny'][sid] = ist['id']
    imp.wczytaj_istniejace('mecze', importuj.TRASY['mecze'], {'leagues': id_liga, 'seasons': id_sezon})
    wynik = {'zmienione': [], 'bez_zmian': 0, 'pominiete': [], 'brak_w_wp': [], 'bledy': []}
    for m in mecze:
        opis = ' - '.join(nazwy_dr.get(str(t)) or 'Do ustalenia' for t in m['teams'])
        ist = imp.istniejace['mecze'].get(str(m['id']))
        zr = importuj.tekst_zrodla(m)
        if ist is None:
            wynik['brak_w_wp'].append(f'{opis}: źródło: {zr}')
            continue
        w_wp = tekst_wp(ist['wp'])
        if ist['zablokowany']:
            wynik['pominiete'].append(f'{opis}: źródło: {zr}, WP: {w_wp} ' + ('(zgodne)' if zr == w_wp else '(RÓŻNICA, zostaje wartość z WP)') + f' [{ist["blokada"]}]')
            continue
        imp.id_wp['mecze'][m['id']] = ist['id']
        przed = len(imp.stany_zywo)
        try:
            if m['results'] and zr != w_wp:                       # wynik końcowy: tylko pole results (bez czyszczenia składu i statystyk)
                if not na_sucho:
                    wyniki = {str(imp.id_wp['druzyny'][t]): v for t, v in m['results'].items() if t in imp.id_wp['druzyny']}
                    if wyniki:
                        wp.zaktualizuj(importuj.TRASY['mecze'], ist['id'], {'results': wyniki})
            importuj._zapisz_stan_zywo(imp, wp, m, opis, ist, na_sucho)
        except Exception as e:                                    # jeden zły mecz nie przerywa odświeżania
            wynik['bledy'].append(f'{opis}: {e}')
            continue
        if zr != w_wp or len(imp.stany_zywo) > przed:
            wynik['zmienione'].append(f'{opis}: było w WP: {w_wp}, ze źródła: {zr}')
        else:
            wynik['bez_zmian'] += 1
    wynik['bledy'] += imp.liczniki['mecze'].uwagi
    return wynik


def podsumowanie(nazwa, zrodlo, liczba_meczow, zapytania, wynik, na_sucho):
    w = [('NA SUCHO (nic nie zapisano): ' if na_sucho else '') + f'ODŚWIEŻENIE WYNIKÓW: {nazwa} ({zrodlo})',
         f'Źródło odpowiadało: tak ({liczba_meczow} meczów ligi, zapytań: {zapytania}).',
         f'Zmieniono meczów: {len(wynik["zmienione"])}' + ('' if not wynik['zmienione'] else ':')]
    w += [f'  - {z}' for z in wynik['zmienione']]
    w.append(f'Bez zmian: {wynik["bez_zmian"]}')
    w.append(f'Pominięte, bo stan i wynik ustala użytkownik (w tym mecz transmitowany): {len(wynik["pominiete"])}' + ('' if not wynik['pominiete'] else ':'))
    w += [f'  - {p}' for p in wynik['pominiete']]
    if wynik['brak_w_wp']:
        w.append(f'Mecze ze źródła, których nie ma w WP ({len(wynik["brak_w_wp"])}; nie tworzę ich, użyj pełnego importu):')
        w += [f'  - {p}' for p in wynik['brak_w_wp'][:20]]
    if wynik['bledy']:
        w.append(f'BŁĘDY ({len(wynik["bledy"])}):')
        w += [f'  - {b}' for b in wynik['bledy'][:20]]
    if wynik['zmienione'] and not na_sucho:
        w.append('Aby zmiany zobaczył moduł: „Pobierz z WP” (strona Rozgrywki WP).')
    return '\n'.join(w)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('modul', nargs='?', choices=sorted(ZRODLA))
    ap.add_argument('--na-sucho', action='store_true')
    ap.add_argument('--liga', help='id ligi w źródle (domyślnie z bieżącego wyboru rozgrywek modułu)')
    ap.add_argument('--sezon', help='id sezonu w źródle (domyślnie z bieżącego wyboru rozgrywek modułu)')
    ap.add_argument('--cache', help='katalog pamięci podręcznej źródła (do prób; wymaga --na-sucho albo --stare-dane-ok)')
    ap.add_argument('--stare-dane-ok', action='store_true')
    a = ap.parse_args(argv)
    if a.cache and not a.na_sucho and not a.stare_dane_ok:
        sys.exit('Odmowa: --cache w prawdziwym odświeżeniu czytałby stare dane zamiast stanu źródła na żywo. Bez --cache albo --na-sucho; świadomie: --stare-dane-ok.')
    klucz = a.modul or rozpoznaj_modul()
    if not klucz:
        sys.exit('Nie rozpoznaję działającego modułu. Uruchom: odswiez-wyniki.bat nalf   albo   odswiez-wyniki.bat garbarnia')
    folder = ZRODLA[klucz]['modul']
    wybor = {'liga': a.liga, 'sezon': a.sezon, 'nazwa': f'liga {a.liga}, sezon {a.sezon}'} if a.liga and a.sezon else wybor_rozgrywek(folder)
    if not wybor:
        sys.exit(f'Moduł {folder} nie ma wybranych rozgrywek WP (strona Rozgrywki WP) i nie podano --liga ze --sezon.')
    wp, port, mod_id = importuj.polacz_z_wp(folder)
    port_env = os.environ.get('BM_WP_PORT')
    if port_env:
        wp.url = f'http://127.0.0.1:{int(port_env)}'               # próby na kopii WP (np. 8099)
    zrodlo = ZRODLA[klucz].get('zrodlo', klucz)
    print(f'Odświeżanie wyników: {wybor["nazwa"]}, moduł {mod_id}, WP 127.0.0.1:{port_env or port}{" [NA SUCHO]" if a.na_sucho else ""}')
    try:
        with Blokada(importuj.wp_dir() / 'odswiez-wyniki.lock'):
            try:
                mecze, zapytania = pobierz_ze_zrodla(klucz, wybor['liga'], wybor['sezon'], a.cache)
            except SystemExit:
                raise
            except Exception as e:
                sys.exit(f'ŹRÓDŁO NIE ODPOWIADA ({e}). Nic nie zmieniono w WP; spróbuj później albo wpisz dane ręcznie w module.')
            if not mecze:
                sys.exit('Źródło nie zwróciło żadnych meczów tej ligi i sezonu. Nic nie zmieniono.')
            try:
                wynik = odswiez(wp, zrodlo, mecze, wybor['liga'], wybor['sezon'], a.na_sucho)
            except WpRestError as e:
                sys.exit(f'Błąd rozmowy z WP: {e}. Czy instancja WP działa?')
    except Zajete as e:
        sys.exit(str(e))
    print(podsumowanie(wybor['nazwa'], zrodlo, len(mecze), zapytania, wynik, a.na_sucho))
    return 1 if wynik['bledy'] else 0


if __name__ == '__main__':
    sys.exit(main())
