"""Kopia i zerowanie danych przed importem z zewnętrznych źródeł (etap I0).

    python tools/import_wp/zerowanie.py lista                    # co zostanie wyzerowane, co zostaje (bez zmian w czymkolwiek)
    python tools/import_wp/zerowanie.py kopia                    # kopia baz modułów, logo i baz instancji WP (nic nie zeruje)
    python tools/import_wp/zerowanie.py zeruj --kopia <katalog> --tak       # zeruje dane rozgrywek w bazach modułów
    python tools/import_wp/zerowanie.py zeruj-wp --kopia <katalog> --tak    # odtwarza instancje WP z szablonu (puste)

Zerowane są wyłącznie dane rozgrywek i transmisji: tabele korzeniowe (sezony, ligi, drużyny, zawodnicy, mecze), wszystko, co przez klucz obcy
od nich zależy, oraz sesje transmisji. Ustawienia (kamery, stadiony, banery, tła, motywy, komentatorzy, sędziowie, typy zdarzeń, konta
pomocników, wpisy i ustawienia scraperów) zostają. Zerowanie wymaga istniejącej kopii (manifest.json) i flagi --tak.
Tylko biblioteka standardowa; nie dotyka folderu transmisyjnego broadcast-modules."""
import argparse
import hashlib
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULES = ('futsal_nalf', 'garbarnia')                     # foldery modułów
KORZENIE = ('seasons', 'leagues', 'teams', 'players', 'games')
SESJE = ('broadcast_sessions',)                            # sesje transmisji: dane, choć bez klucza obcego do korzeni
POMIN = ('settings', 'alembic_version')                    # nigdy nie zerowane w całości
# Tabele zależne od lig, ale zawierające adresy i identyfikatory starych scraperów: zerowane z ligami, ale eksportowane do kopii
EKSPORT_ADRESOW = ('league_scraper_urls', 'league_foreign_ids')


def polacz(db_path, tylko_odczyt=True):
    uri = f'file:{Path(db_path).as_posix()}?mode={"ro" if tylko_odczyt else "rw"}'
    return sqlite3.connect(uri, uri=True)


def tabele(con):
    return [r[0] for r in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]


def analiza(con):
    """Zwraca {'zero': {tabela: powód}, 'zostaje': [tabela], 'settings_null': [kolumny], 'licznosci': {tabela: n}}."""
    wszystkie = tabele(con)
    fk = {t: sorted({r[2] for r in con.execute(f'pragma foreign_key_list("{t}")')}) for t in wszystkie}
    zero = {t: 'tabela korzeniowa (dane rozgrywek)' for t in KORZENIE if t in wszystkie}
    for t in SESJE:
        if t in wszystkie:
            zero[t] = 'sesje transmisji'
    zmiana = True
    while zmiana:
        zmiana = False
        for t in wszystkie:
            if t in zero or t in POMIN:
                continue
            ref = [r for r in fk[t] if r in zero]
            if ref:
                zero[t] = 'klucz obcy do ' + ', '.join(ref)
                zmiana = True
    settings_null = []
    if 'settings' in wszystkie:
        settings_null = [r[3] for r in con.execute('pragma foreign_key_list("settings")') if r[2] in zero]
    return {
        'zero': dict(sorted(zero.items())),
        'zostaje': [t for t in wszystkie if t not in zero],
        'settings_null': sorted(settings_null),
        'licznosci': {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in wszystkie},
    }


def modul_db(modul):
    return REPO / 'modules' / modul / 'instance' / 'database.db'


def raport_listy(modul):
    con = polacz(modul_db(modul))
    try:
        a = analiza(con)
    finally:
        con.close()
    wiersze = [f'== {modul} ({modul_db(modul)})', 'ZEROWANE:']
    for t, powod in a['zero'].items():
        wiersze.append(f'  {t:<28} {a["licznosci"][t]:>7} wierszy   ({powod})')
    wiersze.append('ZOSTAJE:')
    for t in a['zostaje']:
        wiersze.append(f'  {t:<28} {a["licznosci"][t]:>7} wierszy')
    wiersze.append(f'W tabeli settings wskaźniki ustawiane na NULL: {", ".join(a["settings_null"]) or "(brak)"}')
    zal = [t for t in EKSPORT_ADRESOW if t in a['zero']]
    if zal:
        wiersze.append('ZALEŻNE OD LIG (zerowane razem z nimi, ale z eksportem do kopii): ' + ', '.join(f'{t} ({a["licznosci"][t]})' for t in zal))
    return '\n'.join(wiersze), a


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for blok in iter(lambda: f.read(1 << 20), b''):
            h.update(blok)
    return h.hexdigest()


def wp_instancje():
    """Bloki wp z module.json: {modul: {'port', 'db', 'template', 'title'}}."""
    out = {}
    for m in MODULES:
        data = json.loads((REPO / 'modules' / m / 'module.json').read_text(encoding='utf-8-sig'))
        blok = data.get('wp')
        if isinstance(blok, dict):
            port = int(blok['port'])
            out[m] = {'id': data['id'], 'port': port, 'db': blok.get('db') or f'p{port}', 'template': blok.get('template') or '_szablon',
                      'title': blok.get('title') or ''}
    return out


def port_zajety(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def eksport_adresow(con):
    """Adresy i identyfikatory starych scraperów z nazwami lig i sezonów (do odtworzenia po ponownym założeniu lig)."""
    wynik = {}
    ligi = {r[0]: {'liga': r[1], 'sezon': r[2]} for r in con.execute(
        'select l.id, l.name, s.name from leagues l left join seasons s on s.id = l.season_id')}
    skr = {r[0]: r[1] for r in con.execute('select id, folder from scrapers')} if 'scrapers' in tabele(con) else {}
    for t in EKSPORT_ADRESOW:
        if t not in tabele(con):
            continue
        kol = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
        wiersze = []
        for r in con.execute(f'select * from "{t}"'):
            d = dict(zip(kol, r))
            d['_liga'] = ligi.get(d.get('league_id'))
            d['_scraper'] = skr.get(d.get('scraper_id'))
            wiersze.append(d)
        wynik[t] = wiersze
    return wynik


def kopia(katalog=None):
    katalog = Path(katalog) if katalog else REPO / 'wp-local' / 'kopie' / f'przed-importem-{date.today().isoformat()}'
    if katalog.exists() and any(katalog.iterdir()):
        raise SystemExit(f'Katalog kopii już istnieje i nie jest pusty: {katalog}. Niczego nie nadpisuję.')
    katalog.mkdir(parents=True, exist_ok=True)
    manifest = {'utworzono': datetime.now().isoformat(timespec='seconds'), 'moduly': {}, 'wp': {}, 'logo': None}
    for m in MODULES:
        zrodlo = modul_db(m)
        cel = katalog / m
        cel.mkdir()
        src = polacz(zrodlo)
        dst = sqlite3.connect(cel / 'database.db')
        try:
            src.backup(dst)                        # spójna kopia także przy otwartym pliku
        finally:
            dst.close()
        con = polacz(cel / 'database.db')
        try:
            (cel / 'adresy_scraperow.json').write_text(json.dumps(eksport_adresow(con), ensure_ascii=False, indent=2, default=str), encoding='utf-8')
            licz = analiza(con)['licznosci']
        finally:
            con.close()
            src.close()
        wp_json = zrodlo.parent / 'wp_rozgrywki.json'
        if wp_json.exists():
            shutil.copy2(wp_json, cel / 'wp_rozgrywki.json')
        manifest['moduly'][m] = {'sha256': sha256(cel / 'database.db'), 'licznosci': licz}
    logo = REPO / 'modules' / 'static' / 'images' / 'logos'
    if logo.exists():
        shutil.copytree(logo, katalog / 'logos')
        manifest['logo'] = {'pliki': sum(1 for p in (katalog / 'logos').rglob('*') if p.is_file())}
    for m, w in wp_instancje().items():
        baza = REPO / 'wp-local' / 'databases' / w['db']
        if baza.exists():
            shutil.copytree(baza, katalog / 'wp' / w['db'])
            manifest['wp'][w['db']] = {'sha256': sha256(katalog / 'wp' / w['db'] / '.ht.sqlite')}
    (katalog / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return katalog, manifest


def sprawdz_kopie(katalog):
    katalog = Path(katalog)
    manifest = katalog / 'manifest.json'
    if not manifest.exists():
        raise SystemExit(f'Brak kopii: {manifest} nie istnieje. Najpierw uruchom polecenie "kopia".')
    dane = json.loads(manifest.read_text(encoding='utf-8'))
    for m, info in dane['moduly'].items():
        plik = katalog / m / 'database.db'
        if not plik.exists() or sha256(plik) != info['sha256']:
            raise SystemExit(f'Kopia uszkodzona albo zmieniona: {plik}')
    return dane


def zeruj_modul(modul, db_path=None):
    """Zeruje dane rozgrywek w bazie modułu. Zwraca {'przed': {...}, 'po': {...}}."""
    db_path = db_path or modul_db(modul)
    con = polacz(db_path, tylko_odczyt=False)
    try:
        a = analiza(con)
        con.execute('pragma foreign_keys = off')
        con.execute('begin')
        for t in a['zero']:
            con.execute(f'delete from "{t}"')
        if 'sqlite_sequence' in tabele(con) or con.execute("select 1 from sqlite_master where name='sqlite_sequence'").fetchone():
            con.executemany('delete from sqlite_sequence where name = ?', [(t,) for t in a['zero']])
        for kol in a['settings_null']:
            con.execute(f'update settings set "{kol}" = null')
        con.commit()
        po = analiza(con)['licznosci']
        con.execute('vacuum')
    finally:
        con.close()
    return {'przed': a['licznosci'], 'po': po, 'zerowane': list(a['zero'])}


def zeruj_wszystko(katalog_kopii):
    sprawdz_kopie(katalog_kopii)
    if port_zajety(8081):
        raise SystemExit('Port 8081 (moduł) jest zajęty: zatrzymaj moduł przed zerowaniem baz.')
    raporty = {}
    for m in MODULES:
        raporty[m] = zeruj_modul(m)
        plik = modul_db(m).parent / 'wp_rozgrywki.json'
        if plik.exists():
            plik.unlink()                              # wskazuje rozgrywki z usuniętej instancji WP; kopia jest w katalogu kopii
    return raporty


def zeruj_wp(katalog_kopii):
    sprawdz_kopie(katalog_kopii)
    wynik = {}
    php = REPO / 'wp-local' / 'php' / 'php.exe'
    cli = REPO / 'wp-local' / 'wp-cli.phar'
    site = REPO / 'wp-local' / 'wordpress'
    for m, w in wp_instancje().items():
        if port_zajety(w['port']):
            raise SystemExit(f'Port {w["port"]} (WP modułu {m}) jest zajęty: zatrzymaj instancję WP przed odtworzeniem bazy.')
        baza = REPO / 'wp-local' / 'databases' / w['db']
        szablon = REPO / 'wp-local' / 'databases' / w['template'] / '.ht.sqlite'
        if not szablon.exists():
            raise SystemExit(f'Brak szablonu bazy: {szablon}')
        if baza.exists():
            if not (Path(katalog_kopii) / 'wp' / w['db'] / '.ht.sqlite').exists():
                raise SystemExit(f'Kopia nie zawiera bazy {w["db"]}: nie usuwam jej.')
            shutil.rmtree(baza)
        baza.mkdir(parents=True)
        shutil.copy2(szablon, baza / '.ht.sqlite')
        (baza / '.htaccess').write_text('DENY FROM ALL', encoding='utf-8')
        (baza / 'index.php').write_text('<?php // Silence is gold. ?>', encoding='utf-8')
        tytul = 'ustawiono' if w['title'] else 'bez tytułu'
        if w['title']:
            env = {**__import__('os').environ, 'BM_DB': w['db'], 'BM_PORT': str(w['port'])}
            r = subprocess.run([str(php), str(cli), f'--path={site}', 'option', 'update', 'blogname', w['title']], env=env, cwd=REPO / 'wp-local',
                               capture_output=True, text=True)
            tytul = 'ustawiono' if r.returncode == 0 else f'NIE ustawiono ({r.stderr.strip()[:120]})'
        wynik[m] = {'baza': w['db'], 'tytul': tytul}
    return wynik


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('polecenie', choices=('lista', 'kopia', 'zeruj', 'zeruj-wp'))
    ap.add_argument('--kopia', help='katalog kopii (dla kopia: gdzie utworzyć; dla zeruj*: z której korzystać)')
    ap.add_argument('--tak', action='store_true', help='potwierdzenie wykonania zmian')
    a = ap.parse_args(argv)
    if a.polecenie == 'lista':
        for m in MODULES:
            print(raport_listy(m)[0])
            print()
    elif a.polecenie == 'kopia':
        katalog, manifest = kopia(a.kopia)
        print(f'Kopia zapisana w {katalog}')
        for m, info in manifest['moduly'].items():
            print(f'  {m}: baza skopiowana, wierszy w teams={info["licznosci"].get("teams")}, games={info["licznosci"].get("games")}')
        print(f'  logo: {manifest["logo"]}; instancje WP: {sorted(manifest["wp"])}')
    else:
        if not a.kopia:
            sys.exit('Podaj --kopia <katalog>.')
        if not a.tak:
            sys.exit('To polecenie zmienia dane. Dodaj --tak, gdy lista z "lista" została zaakceptowana.')
        if a.polecenie == 'zeruj':
            for m, r in zeruj_wszystko(a.kopia).items():
                print(f'== {m}: wyzerowano {len(r["zerowane"])} tabel')
                for t in r['zerowane']:
                    print(f'  {t:<28} {r["przed"][t]:>7} -> {r["po"][t]}')
        else:
            for m, r in zeruj_wp(a.kopia).items():
                print(f'{m}: baza {r["baza"]} odtworzona z szablonu (tytuł: {r["tytul"]})')


if __name__ == '__main__':
    main()
