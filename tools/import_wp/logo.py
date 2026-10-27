"""Loga i nazwy 14-znakowe drużyn do WP (etap I4): mapa z dotychczasowej bazy modułu (kopia z I0) -> pola bm_logo i bm_name14 drużyn w WP.

    python tools/import_wp/logo.py nalf|garbarnia --kopia <katalog kopii z I0> [--na-sucho]

Pliki logo NIE są kopiowane ani zmieniane: leżą w modules/static/images/logos/<moduł>/ (poza gitem), a nakładki czytają je z modułu jako
http://localhost:8081/<logo_path>. W WP zapisujemy tylko ścieżkę względną „<folder>/<plik>” (bm_logo); W7 przepisze ją do teams.logo_path
jako static/images/logos/<folder>/<plik>. Dopasowanie drużyny w WP do starej: NALF po slugu strony drużyny (stary identyfikator = slug, a importer
nadaje drużynom w WP ten sam slug), Garbarnia po hashu Superscore (bm_source_id); w drugiej kolejności po nazwie (bez wielkości liter i polskich znaków).
Drużynom, których stara baza nie wskazuje działającego pliku (logo domyślne albo plik, którego nie ma), importer szuka pliku w folderze logo modułu po NAZWIE PLIKU
(dokładna zgodność z nazwą drużyny bez spacji i polskich znaków, nazwa drużyny zaczynająca się od nazwy pliku, albo nazwa pliku będąca jednym słowem nazwy drużyny); tylko
wtedy, gdy wynik jest jednoznaczny (jeden plik na drużynę i jedna drużyna na plik). Takie dopasowania są wypisane osobno do sprawdzenia.
Powtarzalne: drużyna, której pola już się zgadzają, nie jest wysyłana. Niczego nie usuwa."""
import argparse
import html
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importuj  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCRAPER_FOLDER = {'nalf': 'nalffutsal', 'garbarnia': 'superscore'}        # źródło stałych identyfikatorów drużyn w starej bazie
STATUSY = 'publish,future,draft,pending,private'


def normalizuj(nazwa):
    t = unicodedata.normalize('NFKD', html.unescape(nazwa or '')).replace('ł', 'l').replace('Ł', 'L')
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return ' '.join(t.casefold().split())


def plik_logo(logo_path):
    """„/static//images/logos/garbarnia/Garbarnia.png” -> „garbarnia/Garbarnia.png”; logo domyślne i puste -> None."""
    if not logo_path:
        return None
    czesci = [c for c in str(logo_path).replace('\\', '/').split('/') if c]
    if len(czesci) < 2 or czesci[-1].lower() == 'default.png':
        return None
    return f'{czesci[-2]}/{czesci[-1]}'


def _zwarta(tekst):
    return ''.join(normalizuj(tekst).split())


def _trzon_pliku(nazwa_pliku):
    """„10 - wroblowianka.png” -> „wroblowianka” (bez numeru porządkowego na początku, rozszerzenia i spacji)."""
    t = Path(nazwa_pliku).stem
    t = t.lstrip('0123456789 -_')
    return _zwarta(t)


def dopasuj_pliki_po_nazwie(druzyny, pliki):
    """druzyny: [(klucz, nazwa)] bez działającego logo; pliki: ['folder/plik.png'] wolne w folderze. Zwraca {klucz: plik} tylko dla dopasowań
    jednoznacznych (każdy plik dla jednej drużyny i każda drużyna z jednym plikiem na najwyższym poziomie dopasowania)."""
    def poziom(nazwa, plik):
        trzon, zwarta = _trzon_pliku(plik), _zwarta(nazwa)
        slowa = normalizuj(nazwa).split()
        if not trzon:
            return 0
        if trzon == zwarta:
            return 3
        if len(trzon) >= 5 and (zwarta.startswith(trzon) or (len(zwarta) >= 5 and trzon.startswith(zwarta))):
            return 2
        if len(trzon) >= 5 and trzon in slowa:
            return 1
        return 0
    kandydaci = {k: {} for k, _ in druzyny}
    for k, nazwa in druzyny:
        for p in pliki:
            lvl = poziom(nazwa, p)
            if lvl:
                kandydaci[k][p] = lvl
    wynik = {}
    for k, _ in druzyny:
        if not kandydaci[k]:
            continue
        najwyzszy = max(kandydaci[k].values())
        najlepsze = [p for p, l in kandydaci[k].items() if l == najwyzszy]
        if len(najlepsze) != 1:
            continue
        plik = najlepsze[0]
        konkurenci = [k2 for k2, _ in druzyny if k2 != k and kandydaci[k2].get(plik, 0) >= najwyzszy]
        if konkurenci:
            continue                                     # ten sam plik pasuje równie dobrze do innej drużyny: niejednoznaczne
        wynik[k] = plik
    return wynik


def mapa_ze_starej_bazy(baza, folder_scrapera):
    """Lista drużyn starej bazy: {'klucz' (identyfikator ze źródła albo None), 'nazwa', 'name14', 'logo'}."""
    con = sqlite3.connect(f'file:{Path(baza).as_posix()}?mode=ro', uri=True)
    try:
        fid = {}
        for team_id, foreign in con.execute("select f.team_id, f.foreign_id from team_foreign_ids f join scrapers s on s.id = f.scraper_id where s.folder = ?",
                                            (folder_scrapera,)):
            fid[team_id] = foreign.split('/')[-1]               # Superscore „slug/hash” -> hash; NALF: slug strony drużyny
        wynik = []
        for tid, nazwa, n14, logo in con.execute('select id, name, name_14, logo_path from teams'):
            wynik.append({'klucz': fid.get(tid), 'nazwa': nazwa, 'name14': (n14 or '').strip(), 'logo': plik_logo(logo)})
        return wynik
    finally:
        con.close()


def wczytaj_druzyny_wp(wp):
    wynik = []
    for r in wp.pobierz_wszystko('sportspress/v2/teams', {'_fields': 'id,title,slug,meta', 'status': STATUSY}):
        t = r.get('title')
        meta = r.get('meta') or {}
        wynik.append({'id': r['id'], 'nazwa': html.unescape(t.get('rendered') if isinstance(t, dict) else (t or '')), 'slug': r.get('slug') or '',
                      'zrodlo_id': str(meta.get('bm_source_id') or ''), 'logo': meta.get('bm_logo') or '', 'name14': meta.get('bm_name14') or ''})
    return wynik


def dopasuj(stare, wp_druzyny, zrodlo):
    """Zwraca (pary [(wp, stara, 'po id'|'po nazwie')], bez_pary_wp, bez_pary_stare)."""
    po_kluczu = {s['klucz']: s for s in stare if s['klucz']}
    po_nazwie = {}
    for s in stare:
        po_nazwie.setdefault(normalizuj(s['nazwa']), s)
    uzyte, pary, bez = set(), [], []
    for w in wp_druzyny:
        klucz = w['slug'] if zrodlo == 'nalf' else w['zrodlo_id']
        s, jak = po_kluczu.get(klucz), 'po identyfikatorze'
        if s is None or id(s) in uzyte:
            s, jak = po_nazwie.get(normalizuj(w['nazwa'])), 'po nazwie'
        if s is None or id(s) in uzyte:
            bez.append(w)
            continue
        uzyte.add(id(s))
        pary.append((w, s, jak))
    bez_stare = [s for s in stare if id(s) not in uzyte]
    return pary, bez, bez_stare


def zastosuj(wp, pary, katalog_logo, na_sucho=False, wolne_pliki=()):
    """Zapisuje bm_logo i bm_name14. Zwraca słownik liczników i list do raportu. wolne_pliki: pliki z folderu logo do dopasowania po nazwie pliku."""
    r = {'zapisane': 0, 'bez_zmian': 0, 'brak_pliku': [], 'bez_logo': [], 'name14_za_dlugie': [], 'po_nazwie': [], 'z_nazwy_pliku': [],
         'bez_pliku_wcale': [], 'powtorzone': []}
    katalog_logo = Path(katalog_logo)
    dziala = lambda s: bool(s['logo'] and (katalog_logo / s['logo']).exists())
    uzycia = {}
    for _, s, _ in pary:
        if dziala(s):
            uzycia[s['logo']] = uzycia.get(s['logo'], 0) + 1
    # logo „podejrzane”: ten sam plik wskazuje kilka drużyn, a nazwa pliku nie pasuje do nazwy tej drużyny (typowo pomyłka przy ręcznym wyborze)
    podejrzane = {w['id'] for w, s, _ in pary if dziala(s) and uzycia[s['logo']] > 1 and not dopasuj_pliki_po_nazwie([(w['id'], w['nazwa'])], [s['logo']])}
    bez_logo = [(w['id'], w['nazwa']) for w, s, _ in pary if not dziala(s) or w['id'] in podejrzane]
    zajete = {s['logo'] for w, s, _ in pary if dziala(s) and w['id'] not in podejrzane}
    z_nazwy = dopasuj_pliki_po_nazwie(bez_logo, [p for p in wolne_pliki if p not in zajete])
    for w, s, jak in pary:
        meta, logo = {}, s['logo']
        if jak == 'po nazwie':
            r['po_nazwie'].append(f'{w["nazwa"]} (stara baza: {s["nazwa"]})')
        if (not dziala(s) or w['id'] in podejrzane) and w['id'] in z_nazwy:
            if w['id'] in podejrzane:
                r['powtorzone'].append(f'{w["nazwa"]}: stara baza wskazywała {logo} (plik użyty też przez inną drużynę), wybrano {z_nazwy[w["id"]]}')
            elif logo:
                r['brak_pliku'].append(f'{w["nazwa"]}: {logo}')
            logo = z_nazwy[w['id']]
            r['z_nazwy_pliku'].append(f'{w["nazwa"]} <- {logo}')
        elif w['id'] in podejrzane:
            r['powtorzone'].append(f'{w["nazwa"]}: plik {logo} użyty także przez inną drużynę, a pliku pasującego do nazwy brak (zostaje wskazanie ze starej bazy)')
        if logo and (katalog_logo / logo).exists():
            if w['logo'] != logo:
                meta['bm_logo'] = logo
        elif logo:
            r['brak_pliku'].append(f'{w["nazwa"]}: {logo}')
        else:
            r['bez_logo'].append(w['nazwa'])
        n14 = s['name14']
        if n14 and len(n14) <= 14:
            if w['name14'] != n14:
                meta['bm_name14'] = n14
        elif n14:
            r['name14_za_dlugie'].append(f'{w["nazwa"]}: „{n14}”')
        if not meta:
            r['bez_zmian'] += 1
            continue
        if not na_sucho:
            wp.zaktualizuj('sportspress/v2/teams', w['id'], {'meta': meta})
        r['zapisane'] += 1
    return r


def raport(modul, pary, bez_wp, bez_stare, r, pliki_nieuzyte, na_sucho):
    w = [('NA SUCHO: ' if na_sucho else '') + f'loga i nazwy 14-znakowe, moduł {modul}',
         f'  dopasowane drużyny: {len(pary)} (po identyfikatorze {sum(1 for p in pary if p[2] == "po identyfikatorze")}, po nazwie {len(r["po_nazwie"])})',
         f'  zapisane w WP: {r["zapisane"]}, bez zmian: {r["bez_zmian"]}']
    if r['po_nazwie']:
        w.append('  dopasowane po nazwie (sprawdź): ' + '; '.join(r['po_nazwie']))
    if bez_wp:
        w.append(f'  drużyny w WP bez wpisu w starej bazie ({len(bez_wp)}): ' + ', '.join(x['nazwa'] for x in bez_wp) + ' (zostają bez logo i bez nazwy 14-znakowej z mapy)')
    if bez_stare:
        w.append(f'  drużyny starej bazy bez pary w WP ({len(bez_stare)}): ' + ', '.join(x['nazwa'] for x in bez_stare) + ' (inny sezon lub liga)')
    if r['z_nazwy_pliku']:
        w.append(f'  logo dopasowane po NAZWIE PLIKU, nie ze starej bazy ({len(r["z_nazwy_pliku"])}; sprawdź na antenie): ' + '; '.join(r['z_nazwy_pliku']))
    if r['powtorzone']:
        w.append(f'  UWAGA, ten sam plik logo wskazuje kilka drużyn w starej bazie ({len(r["powtorzone"])}; prawdopodobna pomyłka): ' + '; '.join(r['powtorzone']))
    if r['bez_logo']:
        w.append(f'  drużyny bez żadnego logo (zostanie logo domyślne) ({len(r["bez_logo"])}): ' + ', '.join(r['bez_logo']))
    if r['brak_pliku']:
        w.append(f'  UWAGA, stara baza wskazuje plik logo, którego nie ma na dysku ({len(r["brak_pliku"])}): ' + '; '.join(r['brak_pliku']))
    if r['name14_za_dlugie']:
        w.append('  UWAGA, nazwa 14-znakowa dłuższa niż 14 znaków (pominięta): ' + '; '.join(r['name14_za_dlugie']))
    if pliki_nieuzyte:
        w.append(f'  pliki logo w folderze modułu bez przypisania do drużyny z tego sezonu ({len(pliki_nieuzyte)}): ' + ', '.join(pliki_nieuzyte))
    return '\n'.join(w)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('zrodlo', choices=sorted(SCRAPER_FOLDER))
    ap.add_argument('--kopia', required=True, help='katalog kopii z I0 (zawiera <folder modułu>/database.db)')
    ap.add_argument('--na-sucho', action='store_true')
    a = ap.parse_args(argv)
    konf = importuj.ZRODLA[a.zrodlo]
    wp, port, mod_id = importuj.polacz_z_wp(konf['modul'])
    baza = Path(a.kopia) / konf['modul'] / 'database.db'
    if not baza.exists():
        sys.exit(f'Brak bazy w kopii: {baza}')
    katalog_logo = REPO / 'modules' / 'static' / 'images' / 'logos'
    stare = mapa_ze_starej_bazy(baza, SCRAPER_FOLDER[a.zrodlo])
    wp_druzyny = wczytaj_druzyny_wp(wp)
    if not wp_druzyny:
        sys.exit('W WP nie ma drużyn: najpierw import (import-nalf.bat / import-garbarnia.bat).')
    pary, bez_wp, bez_stare = dopasuj(stare, wp_druzyny, a.zrodlo)
    folder = konf['modul']
    na_dysku = sorted(f'{folder}/{p.name}' for p in (katalog_logo / folder).glob('*') if p.is_file() and p.name.lower() != 'default.png')
    r = zastosuj(wp, pary, katalog_logo, na_sucho=a.na_sucho, wolne_pliki=na_dysku)
    uzyte = {s['logo'] for _, s, _ in pary if s['logo']} | {x.split(' <- ')[1] for x in r['z_nazwy_pliku']}
    print(raport(mod_id, pary, bez_wp, bez_stare, r, [f for f in na_dysku if f not in uzyte], a.na_sucho))
    return 0


if __name__ == '__main__':
    sys.exit(main())
