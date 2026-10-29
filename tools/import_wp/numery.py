"""Numery koszulek ze starej bazy modułu do WP (krok A, jednorazowe narzędzie): pole natywne „number” zawodnika w WP.

    python tools/import_wp/numery.py nalf|garbarnia --kopia <katalog kopii z I0> [--na-sucho]
    python tools/import_wp/numery.py nalf|garbarnia --cofnij <plik raportu z zapisu>

Stara baza (kopia z I0, otwierana tylko do odczytu) daje „propozycje”; numer zawodnika to Player.number, a gdy go brak, najczęstszy numer z jego składów
meczowych (remis = numer niejednoznaczny, pomijany). Numer trafia do WP tylko gdy spełnione są WSZYSTKIE zasady:
  1. numer w WP jest pusty (sprawdzane jeszcze raz tuż przed zapisem; numeru z Superscore ani ręcznego nigdy nie nadpisuje);
  2. ta sama drużyna: stara drużyna zawodnika odpowiada (reguły z logo.py: identyfikator, potem nazwa) jednej z jego OBECNYCH drużyn w WP;
  3. numer z zakresu 1-99;
  4. numer nie powtarza się w żadnej z obecnych drużyn zawodnika (wśród numerów, które drużyna ma dziś w WP, ani wśród proponowanych nowych);
  5. dopasowanie po nazwisku i imieniu (zestaw słów bez polskich znaków i bez kolejności) jest jednoznaczne po obu stronach.
Raport oznacza każdy zapisany numer jako „propozycja ze starej bazy”, wypisuje pominięte z powodami i zapisuje plik JSON (wp-local\\numery-*.json),
z którego działa --cofnij (usuwa tylko te numery, które nadal są dokładnie takie, jak je zapisano). Przed zapisem kopia pliku bazy WP."""
import argparse
import collections
import html
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importuj  # noqa: E402
import logo  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ETYKIETA = 'propozycja ze starej bazy'
NUMER_MIN, NUMER_MAX = 1, 99
STATUSY = 'publish,future,draft,pending,private'


def tokeny(tekst):
    """„Kędzior Grzegorz” i „grzegorz KEDZIOR” -> ten sam zestaw słów (bez polskich znaków, bez kolejności)."""
    return tuple(sorted(logo.normalizuj(tekst).replace('-', ' ').split()))


def _numer_ze_skladow(licznik):
    """Najczęstszy numer ze składów meczowych; remis na szczycie = None (niejednoznaczny)."""
    if not licznik:
        return None
    (n1, c1), *reszta = licznik.most_common(2)
    return None if reszta and reszta[0][1] == c1 else n1


def wczytaj_stara_baze(baza, folder_scrapera):
    """(drużyny, zawodnicy) ze starej bazy; baza otwierana tylko do odczytu."""
    con = sqlite3.connect(f'file:{Path(baza).as_posix()}?mode=ro', uri=True)
    try:
        fid = {}
        for team_id, foreign in con.execute("select f.team_id, f.foreign_id from team_foreign_ids f join scrapers s on s.id = f.scraper_id where s.folder = ?",
                                            (folder_scrapera,)):
            fid[team_id] = foreign.split('/')[-1]
        druzyny = [{'id': tid, 'klucz': fid.get(tid), 'nazwa': nazwa} for tid, nazwa in con.execute('select id, name from teams')]
        skladowe = collections.defaultdict(collections.Counter)
        for pid, num in con.execute('select player_id, number from game_players where number is not null'):
            skladowe[pid][num] += 1
        zawodnicy = []
        for pid, imie, nazwisko, team, numer in con.execute('select id, first_name, last_name, team_id, number from players'):
            if numer is not None:
                nr, zrodlo = numer, 'numer zawodnika'
            else:
                nr, zrodlo = _numer_ze_skladow(skladowe.get(pid)), 'najczęstszy numer ze składów meczowych'
            zawodnicy.append({'id': pid, 'tokeny': tokeny(f'{nazwisko} {imie}'), 'team_id': team, 'nazwa': f'{nazwisko} {imie}'.strip(),
                              'numer': nr, 'zrodlo_numeru': zrodlo if nr is not None else None, 'ma_skladowe': bool(skladowe.get(pid))})
        return druzyny, zawodnicy
    finally:
        con.close()


def _liczba(tekst):
    t = str(tekst if tekst is not None else '').strip()
    return int(t) if t.isdigit() else None


def wczytaj_zawodnikow_wp(wp):
    wynik = []
    for r in wp.pobierz_wszystko('sportspress/v2/players', {'_fields': 'id,title,number,current_teams,teams', 'status': STATUSY}):
        t = r.get('title')
        nazwa = html.unescape(t.get('rendered') if isinstance(t, dict) else (t or ''))
        aktualne = [int(x) for x in (r.get('current_teams') or r.get('teams') or []) if x]
        wynik.append({'id': r['id'], 'nazwa': nazwa, 'tokeny': tokeny(nazwa), 'numer': _liczba(r.get('number')), 'druzyny': aktualne})
    return wynik


def zaplanuj(stare_druzyny, stare_zawodnicy, wp_druzyny, wp_zawodnicy, zrodlo):
    """Czysta funkcja: nic nie zapisuje. Zwraca plan z kategoriami."""
    pary, _, _ = logo.dopasuj(stare_druzyny, wp_druzyny, zrodlo)
    wp_dla_starej = {s['id']: w['id'] for w, s, _ in pary}
    nazwa_druzyny = {w['id']: w['nazwa'] for w in wp_druzyny}
    nazwa_starej = {d['id']: d['nazwa'] for d in stare_druzyny}
    po_tokenach = collections.defaultdict(list)
    for s in stare_zawodnicy:
        po_tokenach[s['tokeny']].append(s)
    plan = {'propozycje': [], 'pominiete': collections.defaultdict(list), 'zgodne_z_wp': 0, 'rozne_od_wp': [], 'liczniki': {}}
    pominiete = plan['pominiete']
    kandydaci = []                                    # (zawodnik WP, stary zawodnik)
    trafione_stare = collections.Counter()
    for z in wp_zawodnicy:
        mozliwi = po_tokenach.get(z['tokeny'], [])
        if not mozliwi:
            continue
        w_druzynie = [s for s in mozliwi if wp_dla_starej.get(s['team_id']) in z['druzyny']]
        if len(w_druzynie) > 1:
            pominiete['niejednoznaczny (kilku zawodników o tej nazwie w starej bazie)'].append(z['nazwa'])
            continue
        if not w_druzynie:
            if any(s['numer'] is not None for s in mozliwi):
                pominiete['inna drużyna niż w starej bazie (transfer?)'].append(f'{z["nazwa"]}: stara baza ' + ', '.join(
                    f'nr {s["numer"]} w drużynie „{nazwa_starej.get(s["team_id"], s["team_id"])}”' for s in mozliwi if s['numer'] is not None))
            continue
        s = w_druzynie[0]
        trafione_stare[s['id']] += 1
        kandydaci.append((z, s))
    for z, s in kandydaci:
        if trafione_stare[s['id']] > 1:
            pominiete['niejednoznaczny (kilku zawodników WP o tej nazwie)'].append(z['nazwa'])
    kandydaci = [(z, s) for z, s in kandydaci if trafione_stare[s['id']] == 1]
    istniejace = collections.defaultdict(collections.Counter)         # drużyna WP -> numery, które ma dziś
    for z in wp_zawodnicy:
        if z['numer'] is not None:
            for d in z['druzyny']:
                istniejace[d][z['numer']] += 1
    propozycje = []
    for z, s in kandydaci:
        if s['numer'] is None:
            pominiete['brak numeru w starej bazie' + (' (remis numerów ze składów)' if s['ma_skladowe'] else '')].append(z['nazwa'])
        elif z['numer'] is not None:
            if z['numer'] == s['numer']:
                plan['zgodne_z_wp'] += 1
            else:
                plan['rozne_od_wp'].append(f'{z["nazwa"]}: w WP {z["numer"]}, stara baza {s["numer"]} (WP zostaje)')
        elif not NUMER_MIN <= s['numer'] <= NUMER_MAX:
            pominiete[f'numer spoza zakresu {NUMER_MIN}-{NUMER_MAX}'].append(f'{z["nazwa"]}: {s["numer"]}')
        else:
            propozycje.append((z, s))
    wolne = []
    for z, s in propozycje:
        zajete = [nazwa_druzyny.get(d, d) for d in z['druzyny'] if istniejace[d][s['numer']] > 0]
        if zajete:
            pominiete['numer zajęty w drużynie przez innego zawodnika'].append(f'{z["nazwa"]}: {s["numer"]} ({", ".join(map(str, zajete))})')
        else:
            wolne.append((z, s))
    w_druzynie_numery = collections.defaultdict(lambda: collections.defaultdict(list))
    for z, s in wolne:
        for d in z['druzyny']:
            w_druzynie_numery[d][s['numer']].append(z['id'])
    kolizje = {zid for d in w_druzynie_numery.values() for lista in d.values() if len(lista) > 1 for zid in lista}
    for z, s in wolne:
        if z['id'] in kolizje:
            pominiete['ten sam numer proponowany kilku zawodnikom drużyny'].append(f'{z["nazwa"]}: {s["numer"]}')
        else:
            plan['propozycje'].append({'id_wp': z['id'], 'nazwa': z['nazwa'], 'druzyny': [nazwa_druzyny.get(d, str(d)) for d in z['druzyny']],
                                       'numer': s['numer'], 'zrodlo_numeru': s['zrodlo_numeru'], 'etykieta': ETYKIETA})
    uzyte = set(trafione_stare)
    plan['liczniki'] = {
        'zawodnicy_stara_baza_z_numerem': sum(1 for s in stare_zawodnicy if s['numer'] is not None),
        'stare_z_numerem_bez_odpowiednika_w_wp': sum(1 for s in stare_zawodnicy if s['numer'] is not None and s['id'] not in uzyte),
        'zawodnicy_wp': len(wp_zawodnicy),
        'do_zapisu': len(plan['propozycje']),
    }
    plan['pominiete'] = dict(pominiete)
    return plan


def zapisz(wp, plan, na_sucho):
    """Zapis numerów do WP. Tuż przed zapisem sprawdza ponownie, że numer w WP nadal jest pusty."""
    wyniki = {'zapisane': [], 'zmienione_w_miedzyczasie': [], 'bledy': []}
    for p in plan['propozycje']:
        if na_sucho:
            wyniki['zapisane'].append(p)
            continue
        try:
            teraz, _ = wp.zadanie('GET', f'sportspress/v2/players/{p["id_wp"]}', params={'_fields': 'id,number'})
            if _liczba(teraz.get('number')) is not None:
                wyniki['zmienione_w_miedzyczasie'].append(f'{p["nazwa"]}: w WP jest już {teraz.get("number")}')
                continue
            wp.zaktualizuj('sportspress/v2/players', p['id_wp'], {'number': p['numer']})
            wyniki['zapisane'].append(p)
        except Exception as e:                                     # jeden zły rekord nie przerywa reszty
            wyniki['bledy'].append(f'{p["nazwa"]}: {e}')
    return wyniki


def cofnij(wp, plik, na_sucho):
    """Usuwa numery zapisane wg raportu, ale tylko te, które nadal są dokładnie takie, jak zapisano."""
    dane = json.loads(Path(plik).read_text(encoding='utf-8'))
    wynik = {'usuniete': [], 'zmienione_pozniej': [], 'bledy': []}
    for p in dane['zapisane']:
        try:
            teraz, _ = wp.zadanie('GET', f'sportspress/v2/players/{p["id_wp"]}', params={'_fields': 'id,number'})
            if _liczba(teraz.get('number')) != p['numer']:
                wynik['zmienione_pozniej'].append(f'{p["nazwa"]}: zapisano {p["numer"]}, w WP jest „{teraz.get("number")}” (zostaje)')
                continue
            if not na_sucho:
                wp.zaktualizuj('sportspress/v2/players', p['id_wp'], {'number': ''})
            wynik['usuniete'].append(p)
        except Exception as e:
            wynik['bledy'].append(f'{p["nazwa"]}: {e}')
    return wynik


def raport(modul, plan, wyniki, na_sucho, plik_raportu=None):
    c = plan['liczniki']
    w = [('NA SUCHO: ' if na_sucho else '') + f'numery koszulek ze starej bazy, moduł {modul}',
         f'  stara baza: zawodników z numerem {c["zawodnicy_stara_baza_z_numerem"]}; zawodników w WP {c["zawodnicy_wp"]}',
         f'  {"DO ZAPISU" if na_sucho else "zapisane"} ({ETYKIETA}): {len(wyniki["zapisane"])}']
    for p in wyniki['zapisane']:
        w.append(f'    - {p["nazwa"]} ({", ".join(p["druzyny"])}): nr {p["numer"]} [{ETYKIETA}; {p["zrodlo_numeru"]}]')
    if wyniki['zmienione_w_miedzyczasie']:
        w.append(f'  POMINIĘTE, numer pojawił się w WP w międzyczasie ({len(wyniki["zmienione_w_miedzyczasie"])}): ' + '; '.join(wyniki['zmienione_w_miedzyczasie']))
    if wyniki['bledy']:
        w.append(f'  BŁĘDY ZAPISU ({len(wyniki["bledy"])}): ' + '; '.join(wyniki['bledy']))
    w.append(f'  już zgodne z WP: {plan["zgodne_z_wp"]}; stare numery bez odpowiednika w WP: {c["stare_z_numerem_bez_odpowiednika_w_wp"]}')
    for powod, lista in sorted(plan['pominiete'].items()):
        w.append(f'  pominięte: {powod} ({len(lista)}):')
        w += [f'    - {x}' for x in lista[:25]]
        if len(lista) > 25:
            w.append(f'    ... i {len(lista) - 25} kolejnych')
    if plan['rozne_od_wp']:
        w.append(f'  numer w WP różny od starej bazy ({len(plan["rozne_od_wp"])}; informacja, WP zostaje):')
        w += [f'    - {x}' for x in plan['rozne_od_wp'][:25]]
    if plik_raportu:
        w.append(f'  raport (do --cofnij): {plik_raportu}')
    return '\n'.join(w)


def kopia_bazy_wp(port, blok_wp):
    """Kopia pliku bazy WP instancji przed zapisem; zwraca ścieżkę albo None."""
    zrodlo = importuj.wp_dir() / 'databases' / (blok_wp.get('db') or f'p{port}') / '.ht.sqlite'
    if not zrodlo.is_file():
        return None
    cel = importuj.wp_dir() / 'kopie-numery' / datetime.now().strftime('%Y%m%d-%H%M%S') / zrodlo.parent.name
    cel.mkdir(parents=True, exist_ok=True)
    shutil.copy2(zrodlo, cel / zrodlo.name)
    return str(cel / zrodlo.name)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('zrodlo', choices=sorted(logo.SCRAPER_FOLDER))
    ap.add_argument('--kopia', help='katalog kopii z I0 (zawiera <folder modułu>/database.db)')
    ap.add_argument('--na-sucho', action='store_true')
    ap.add_argument('--cofnij', metavar='PLIK_RAPORTU', help='usuwa numery zapisane wg tego raportu (tylko niezmienione od zapisu)')
    a = ap.parse_args(argv)
    konf = importuj.ZRODLA[a.zrodlo]
    wp, port, mod_id = importuj.polacz_z_wp(konf['modul'])
    if a.cofnij:
        wynik = cofnij(wp, a.cofnij, a.na_sucho)
        print(('NA SUCHO: ' if a.na_sucho else '') + f'cofnięcie numerów, moduł {mod_id}: usunięte {len(wynik["usuniete"])}, zmienione później (zostają) {len(wynik["zmienione_pozniej"])}, błędy {len(wynik["bledy"])}')
        for x in wynik['zmienione_pozniej'] + wynik['bledy']:
            print('   -', x)
        return 1 if wynik['bledy'] else 0
    if not a.kopia:
        sys.exit('Podaj --kopia <katalog kopii z I0> (albo --cofnij <plik raportu>).')
    baza = Path(a.kopia) / konf['modul'] / 'database.db'
    if not baza.exists():
        sys.exit(f'Brak bazy w kopii: {baza}')
    stare_dr, stare_zaw = wczytaj_stara_baze(baza, logo.SCRAPER_FOLDER[a.zrodlo])
    wp_dr = logo.wczytaj_druzyny_wp(wp)
    if not wp_dr:
        sys.exit('W WP nie ma drużyn: najpierw import (import-nalf.bat / import-garbarnia.bat).')
    plan = zaplanuj(stare_dr, stare_zaw, wp_dr, wczytaj_zawodnikow_wp(wp), a.zrodlo)
    kopia = None
    if not a.na_sucho and plan['propozycje']:
        blok = json.loads((REPO / 'modules' / konf['modul'] / 'module.json').read_text(encoding='utf-8-sig')).get('wp') or {}
        kopia = kopia_bazy_wp(port, blok)
        if kopia:
            print(f'Kopia pliku bazy WP przed zapisem: {kopia}')
    wyniki = zapisz(wp, plan, a.na_sucho)
    plik = importuj.wp_dir() / f'numery-{a.zrodlo}-{datetime.now():%Y%m%d-%H%M%S}{"-na-sucho" if a.na_sucho else ""}.json'
    plik.write_text(json.dumps({'modul': mod_id, 'na_sucho': a.na_sucho, 'etykieta': ETYKIETA, 'czas': datetime.now().isoformat(timespec='seconds'),
                                'kopia_bazy_wp': kopia, 'zapisane': wyniki['zapisane'], 'pominiete': plan['pominiete'], 'rozne_od_wp': plan['rozne_od_wp'],
                                'liczniki': plan['liczniki']}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(raport(mod_id, plan, wyniki, a.na_sucho, str(plik)))
    return 1 if wyniki['bledy'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except importuj.WpRestError as e:
        sys.exit(f'Błąd rozmowy z WP: {e}. Czy instancja działa (wp-nalf.bat albo wp-garbarnia.bat)? Zaraz po starcie pierwsze żądanie bywa wolne: spróbuj ponownie.')
