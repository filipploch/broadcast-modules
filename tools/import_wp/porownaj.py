"""Raport zgodności importu ze stroną źródłową (etap I3): źródło (odczyt na żywo) kontra to, co leży w WP modułu. Niczego nie zapisuje.

    python tools/import_wp/porownaj.py nalf|garbarnia [--sezon <id>] [--cache <katalog>] [--kopia <katalog kopii z I0>]

Sprawdza dla każdej ligi: liczby drużyn, zawodników i meczów (rozegranych i przyszłych), sumę bramek; każdy mecz osobno (data, drużyny, liga,
wynik); tabelę przeliczoną z zaimportowanych wyników (punkty, mecze, bramki) kontra tabelę źródła (NALF: tabela z API; Garbarnia: brak tabeli
w Superscore, więc porównanie wyników z dotychczasową bazą modułu z kopii I0, jeśli podano --kopia); próbkę 5 meczów obok siebie; powtarzalność
(import „na sucho” nie może widzieć nowych ani zmienionych rekordów). Kod wyjścia 1, gdy są rozbieżności."""
import argparse
import html
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importuj  # noqa: E402
import nalf as zrodlo_nalf  # noqa: E402
import superscore as zrodlo_superscore  # noqa: E402



def gole_zrodla(m):
    """Wyniki meczu ze źródła tylko z niepustą liczbą bramek (mecz z pustym wynikiem w API liczy się jako nierozegrany)."""
    return {str(t): v['goals'] for t, v in m['results'].items() if str(v.get('goals', '')) != ''}


def rozegrany_w_zrodle(m):
    g = gole_zrodla(m)
    return bool(g) and len(g) == len([t for t in m['teams'] if t])


def tekst(v):
    return html.unescape(v.get('rendered') if isinstance(v, dict) else (v or ''))


def wczytaj_wp(wp, zrodlo):
    """Rekordy tego źródła z WP, indeksowane identyfikatorem ze źródła; drużyny i ligi przeliczone z id WP na id ze źródła."""
    ligi = {}
    for t in wp.pobierz_wszystko('sportspress/v2/leagues', {'_fields': 'id,slug'}):
        m = re.fullmatch(rf'{re.escape(zrodlo)}-l(.+)', t['slug'])
        if m:
            ligi[t['id']] = m.group(1)
    druzyny, wp_na_zrodlo = {}, {0: '0'}
    for r in wp.pobierz_wszystko('sportspress/v2/teams', {'_fields': 'id,title,leagues,meta', 'status': 'publish,future,draft,pending,private'}):
        meta = r.get('meta') or {}
        if meta.get('bm_source') == zrodlo:
            sid = str(meta['bm_source_id'])
            druzyny[sid] = {'wp': r['id'], 'nazwa': tekst(r['title']), 'ligi': {ligi[l] for l in r.get('leagues') or [] if l in ligi}}
            wp_na_zrodlo[r['id']] = sid
    zawodnicy = {}
    for r in wp.pobierz_wszystko('sportspress/v2/players', {'_fields': 'id,title,leagues,teams,meta', 'status': 'publish,future,draft,pending,private'}):
        meta = r.get('meta') or {}
        if meta.get('bm_source') == zrodlo:
            zawodnicy[str(meta['bm_source_id'])] = {'wp': r['id'], 'nazwa': tekst(r['title']), 'ligi': {ligi[l] for l in r.get('leagues') or [] if l in ligi}}
    mecze = {}
    for r in wp.pobierz_wszystko('sportspress/v2/events', {'_fields': 'id,title,date,leagues,teams,results,meta', 'status': 'publish,future,draft,pending,private'}):
        meta = r.get('meta') or {}
        if meta.get('bm_source') != zrodlo:
            continue
        wyniki = {}
        res = r.get('results')
        for t, v in (res.items() if isinstance(res, dict) else []):          # mecz bez wyniku ma w results pustą listę
            if t != '0' and isinstance(v, dict) and str(v.get('goals', '')) != '' and int(t) in wp_na_zrodlo:
                wyniki[wp_na_zrodlo[int(t)]] = v['goals']
        mecze[str(meta['bm_source_id'])] = {'wp': r['id'], 'tytul': tekst(r['title']), 'data': r.get('date') or '',
                                            'druzyny': [wp_na_zrodlo.get(t, '?') for t in r.get('teams') or []],
                                            'ligi': {ligi[l] for l in r.get('leagues') or [] if l in ligi}, 'wyniki': wyniki}
    return {'druzyny': druzyny, 'zawodnicy': zawodnicy, 'mecze': mecze}


def tabela(mecze):
    """Tabela z wyników {id drużyny: {m, pkt, gz, gs}} (3 pkt za zwycięstwo, 1 za remis); mecze: lista (gospodarz, gość, gole_g, gole_a)."""
    t = {}
    for g, a, gg, ga in mecze:
        for d, za, st in ((g, gg, ga), (a, ga, gg)):
            w = t.setdefault(str(d), {'m': 0, 'pkt': 0, 'gz': 0, 'gs': 0})
            w['m'] += 1
            w['gz'] += za
            w['gs'] += st
            w['pkt'] += 3 if za > st else 1 if za == st else 0
    return t


def kolejnosc(t):
    return sorted(t, key=lambda d: (-t[d]['pkt'], -(t[d]['gz'] - t[d]['gs']), -t[d]['gz'], d))


def mecze_ze_zrodla(dane, liga):
    """Rozegrane mecze ligi ze źródła jako (gospodarz, gość, gole_g, gole_a)."""
    wynik = []
    for m in dane['mecze']:
        if str(liga) in [str(l) for l in m['leagues']] and rozegrany_w_zrodle(m) and len(m['teams']) == 2:
            g, a = (str(t) for t in m['teams'])
            gole = gole_zrodla(m)
            wynik.append((g, a, int(gole[g]), int(gole[a])))
    return wynik


def mecze_z_wp(wp_dane, liga):
    wynik = []
    for m in wp_dane['mecze'].values():
        if liga in m['ligi'] and len(m['druzyny']) == 2 and all(d in m['wyniki'] for d in m['druzyny']):
            g, a = m['druzyny']
            wynik.append((g, a, int(m['wyniki'][g]), int(m['wyniki'][a])))
    return wynik


def porownaj(dane, wp_dane, tabele_zrodla=None, stara_baza=None):
    """Zwraca {'ligi': [...], 'rozbieznosci': [...], 'probka': [...], 'tabela_info': [...]}. Rozbieżność = coś, co trzeba wyjaśnić."""
    roz, ligi_wiersze, info = [], [], []
    nazwy_druzyn = {str(t['id']): t['name'] for t in dane['druzyny']}
    for lid, liga in dane['ligi'].items():
        lid = str(lid)
        z_mecze = [m for m in dane['mecze'] if lid in [str(l) for l in m['leagues']]]
        z_rozegrane = [m for m in z_mecze if rozegrany_w_zrodle(m)]
        w_mecze = [m for m in wp_dane['mecze'].values() if lid in m['ligi']]
        w_rozegrane = [m for m in w_mecze if m['wyniki']]
        wiersz = {
            'liga': liga['name'],
            'druzyny': (sum(1 for t in dane['druzyny'] if lid in [str(l) for l in t['leagues']]), sum(1 for t in wp_dane['druzyny'].values() if lid in t['ligi'])),
            'zawodnicy': (sum(1 for p in dane['zawodnicy'] if lid in [str(l) for l in p['leagues']]), sum(1 for p in wp_dane['zawodnicy'].values() if lid in p['ligi'])),
            'mecze': (len(z_mecze), len(w_mecze)), 'rozegrane': (len(z_rozegrane), len(w_rozegrane)),
            'przyszle': (len(z_mecze) - len(z_rozegrane), len(w_mecze) - len(w_rozegrane)),
            'bramki': (sum(int(g) for m in z_rozegrane for g in gole_zrodla(m).values()),
                       sum(int(g) for m in w_rozegrane for g in m['wyniki'].values()))}
        for k in ('druzyny', 'zawodnicy', 'mecze', 'rozegrane', 'przyszle', 'bramki'):
            if wiersz[k][0] != wiersz[k][1]:
                roz.append(f'{liga["name"]}: {k}: źródło {wiersz[k][0]}, WP {wiersz[k][1]}')
        # tabela przeliczona z wyników źródła i z wyników w WP
        tz, tw = tabela(mecze_ze_zrodla(dane, lid)), tabela(mecze_z_wp(wp_dane, lid))
        for d in sorted(set(tz) | set(tw)):
            if tz.get(d) != tw.get(d):
                roz.append(f'{liga["name"]}: tabela z wyników, {nazwy_druzyn.get(d, d)}: źródło {tz.get(d)}, WP {tw.get(d)}')
        # tabela źródła (NALF): punkty i mecze
        ref = (tabele_zrodla or {}).get(lid)
        if ref:
            for d, w in ref.items():
                mine = tw.get(d)
                if mine is None or (mine['pkt'], mine['m'], mine['gz'], mine['gs']) != (w['pkt'], w['m'], w['gz'], w['gs']):
                    roz.append(f'{liga["name"]}: tabela źródła, {nazwy_druzyn.get(d, d)}: punkty/mecze/bramki w tabeli źródła '
                               f'{w["pkt"]}/{w["m"]}/{w["gz"]}:{w["gs"]}, z wyników w WP '
                               f'{(mine or {}).get("pkt")}/{(mine or {}).get("m")}/{(mine or {}).get("gz")}:{(mine or {}).get("gs")}')
            poz_zrodla = [d for d, _ in sorted(ref.items(), key=lambda kv: kv[1]['pos'])]
            poz_wp = kolejnosc(tw)
            if poz_zrodla != poz_wp:
                nazwa = lambda d: f'{nazwy_druzyn.get(d, d)} ({tw[d]["pkt"]} pkt, {tw[d]["gz"] - tw[d]["gs"]:+d})'
                info.append(f'{liga["name"]}: kolejność w tabeli źródła różni się od prostej kolejności z wyników (punkty, różnica bramek, bramki). '
                            f'Źródło: {" > ".join(nazwa(d) for d in poz_zrodla if d in tw)}. Z wyników: {" > ".join(nazwa(d) for d in poz_wp)}. '
                            f'To zasady rozstrzygania remisów (mała tabela), nie błąd importu, o ile różnią się tylko drużyny z równą liczbą punktów')
        wiersz['tabela'] = len(tz)
        ligi_wiersze.append(wiersz)
    # każdy mecz osobno
    wp_mecze = wp_dane['mecze']
    for m in dane['mecze']:
        w = wp_mecze.get(str(m['id']))
        if w is None:
            roz.append(f'mecz {m["id"]} jest w źródle, brak w WP')
            continue
        if m['date'] and w['data'] != m['date']:
            roz.append(f'mecz {m["id"]}: data źródło {m["date"]}, WP {w["data"]}')
        if [str(t) for t in m['teams']] != w['druzyny']:
            roz.append(f'mecz {m["id"]}: drużyny źródło {m["teams"]}, WP {w["druzyny"]}')
        zr = gole_zrodla(m)
        if zr != w['wyniki']:
            roz.append(f'mecz {m["id"]}: wynik źródło {zr}, WP {w["wyniki"]}')
    zr_ids = {str(m['id']) for m in dane['mecze']}
    nadmiar = sorted(set(wp_mecze) - zr_ids)
    if nadmiar:
        info.append(f'w WP jest {len(nadmiar)} meczów tego źródła, których nie ma w pobranym sezonie (mogą należeć do innych sezonów)')
    # próbka 5 meczów: pierwszy i ostatni rozegrany oraz 3 równomiernie
    rozegrane = [m for m in dane['mecze'] if rozegrany_w_zrodle(m)]
    idx = sorted({0, len(rozegrane) - 1, len(rozegrane) // 4, len(rozegrane) // 2, 3 * len(rozegrane) // 4}) if rozegrane else []
    probka = []
    for i in idx:
        m = rozegrane[i]
        w = wp_mecze.get(str(m['id'])) or {}
        probka.append((m['date'], ' - '.join(nazwy_druzyn.get(str(t), str(t)) for t in m['teams']),
                       ':'.join(gole_zrodla(m).get(str(t), '?') for t in m['teams']),
                       (w.get('data') or '-'), w.get('tytul') or '-', ':'.join(w.get('wyniki', {}).get(str(t), '?') for t in m['teams'])))
    # stara baza modułu (Garbarnia): wyniki meczów zakończonych w obu miejscach
    if stara_baza:
        roz += porownaj_ze_stara_baza(dane, wp_dane, stara_baza, nazwy_druzyn, info)
    return {'ligi': ligi_wiersze, 'rozbieznosci': roz, 'probka': probka, 'info': info}


def porownaj_ze_stara_baza(dane, wp_dane, sciezka, nazwy, info):
    """Wyniki meczów zakończonych w dotychczasowej bazie modułu (kopia I0; pochodzą z tego samego źródła) kontra WP."""
    con = sqlite3.connect(f'file:{Path(sciezka).as_posix()}?mode=ro', uri=True)
    try:
        hasze = {r[0]: r[1].split('/')[-1] for r in con.execute(
            "select team_id, foreign_id from team_foreign_ids where scraper_id = (select id from scrapers where folder = 'superscore')")}
        stare = {}
        for g, a, gg, ga in con.execute('select home_team_id, away_team_id, home_team_goals, away_team_goals from games where status = 2'):
            if g in hasze and a in hasze and gg is not None and ga is not None:
                stare[(hasze[g], hasze[a])] = (gg, ga)
    finally:
        con.close()
    wp_pary = {}
    for m in wp_dane['mecze'].values():                      # ta sama para może grać więcej niż raz (np. puchar): porównujemy z każdym meczem pary
        if len(m['druzyny']) == 2:
            wp_pary.setdefault(tuple(m['druzyny']), []).append(m['wyniki'])
    roz, zgodne, tylko_stara = [], 0, 0
    for (g, a), (gg, ga) in sorted(stare.items()):
        warianty = wp_pary.get((g, a))
        if warianty is None:
            tylko_stara += 1
            continue
        if any((w.get(g), w.get(a)) == (str(gg), str(ga)) for w in warianty):
            zgodne += 1
        elif all(w.get(g) is None for w in warianty):
            info.append(f'stara baza: {nazwy.get(g, g)} - {nazwy.get(a, a)} {gg}:{ga}, w WP mecz bez wyniku')
        else:
            w = next(w for w in warianty if w.get(g) is not None)
            roz.append(f'stara baza kontra WP: {nazwy.get(g, g)} - {nazwy.get(a, a)}: stara baza {gg}:{ga}, WP {w.get(g)}:{w.get(a)}')
    info.append(f'stara baza modułu (kopia): {len(stare)} meczów zakończonych, zgodnych z WP {zgodne}, tylko w starej bazie (inna liga lub sezon) {tylko_stara}')
    return roz


def raport_tekstowy(zrodlo, wynik, powtarzalnosc):
    w = [f'Raport zgodności importu {zrodlo} (źródło na żywo kontra WP)']
    for l in wynik['ligi']:
        w.append(f'== {l["liga"]}')
        for k, n in (('druzyny', 'drużyny'), ('zawodnicy', 'zawodnicy'), ('mecze', 'mecze razem'), ('rozegrane', 'mecze rozegrane'),
                     ('przyszle', 'mecze przyszłe'), ('bramki', 'suma bramek')):
            a, b = l[k]
            w.append(f'  {n:<16} źródło {a:>5}   WP {b:>5}   {"OK" if a == b else "ROZBIEŻNOŚĆ"}')
        w.append(f'  tabela z wyników: {l["tabela"]} drużyn')
    w.append('Próbka meczów (źródło | WP):')
    for d1, t1, r1, d2, t2, r2 in wynik['probka']:
        w.append(f'  {d1}  {t1}  {r1}   |   {d2}  {t2}  {r2}')
    w.append(f'Powtarzalność (import na sucho): {powtarzalnosc}')
    for i in wynik['info']:
        w.append(f'Informacja: {i}')
    if wynik['rozbieznosci']:
        w.append(f'ROZBIEŻNOŚCI ({len(wynik["rozbieznosci"])}):')
        w += [f'  - {r}' for r in wynik['rozbieznosci'][:50]]
        if len(wynik['rozbieznosci']) > 50:
            w.append(f'  ... i {len(wynik["rozbieznosci"]) - 50} kolejnych')
    else:
        w.append('WYNIK: ZGODNE (brak rozbieżności)')
    return '\n'.join(w)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('zrodlo', choices=sorted(importuj.ZRODLA))
    ap.add_argument('--sezon')
    ap.add_argument('--cache')
    ap.add_argument('--kopia', help='katalog kopii z I0 (Garbarnia: porównanie wyników z dotychczasową bazą modułu)')
    a = ap.parse_args(argv)
    konf = importuj.ZRODLA[a.zrodlo]
    wp, port, mod_id = importuj.polacz_z_wp(konf['modul'])
    zrodlo = konf.get('zrodlo', a.zrodlo)
    tabele_zrodla, stara_baza = None, None
    if zrodlo == 'nalf':
        sezon = int(a.sezon or konf['sezon'])
        api = zrodlo_nalf.NalfApi(cache_dir=a.cache)
        dane = zrodlo_nalf.pobierz_sezon(api, sezon, log=lambda *x: None)
        tabele_zrodla = {}
        for t in api.get_all('tables', seasons=sezon, _fields='id,title,leagues,data'):
            for lg in t.get('leagues') or []:
                dd = t.get('data') or {}
                tabele_zrodla[str(lg)] = {str(k): {'pkt': int(v.get('pkt') or 0), 'm': int(v.get('m') or 0), 'gz': int(v.get('gz') or 0),
                                                   'gs': int(v.get('gs') or 0), 'pos': int(v.get('pos') or 0)}
                                          for k, v in dd.items() if k != '0' and isinstance(v, dict)}
    else:
        konf = {**konf, **({'sezon': a.sezon} if a.sezon else {})}
        dane = zrodlo_superscore.pobierz_sezon(zrodlo_superscore.SuperscoreApi(cache_dir=a.cache), konf, log=lambda *x: None)
        if a.kopia:
            stara_baza = Path(a.kopia) / konf['modul'] / 'database.db'
    wp_dane = wczytaj_wp(wp, zrodlo)
    wynik = porownaj(dane, wp_dane, tabele_zrodla, stara_baza)
    imp = importuj.importuj_zrodlo(wp, zrodlo, dane, na_sucho=True, log=lambda *x: None)
    zmiany = sum(l.nowe + l.zmienione for k, l in imp.liczniki.items() if k != 'sezon' or True)
    bledy = sum(l.bledy for l in imp.liczniki.values())
    powt = f'0 nowych i 0 zmienionych rekordów (OK)' if zmiany == 0 and bledy == 0 else f'{zmiany} rekordów do zapisania, {bledy} błędów (ROZBIEŻNOŚĆ)'
    if zmiany or bledy:
        wynik['rozbieznosci'].append('import na sucho widzi rekordy do zapisania albo błędy: ' + powt)
        wynik['info'].append('WP nie jest aktualny względem źródła (źródło zmieniło się od ostatniego importu, np. rozegrano mecz): uruchom import '
                             '(import-nalf.bat / import-garbarnia.bat) i powtórz raport')
    for d in imp.liczniki['zawodnicy'].duplikaty:
        wynik['rozbieznosci'].append('możliwy duplikat zawodnika: ' + d)
    print(raport_tekstowy(zrodlo, wynik, powt))
    return 1 if wynik['rozbieznosci'] else 0


if __name__ == '__main__':
    sys.exit(main())
