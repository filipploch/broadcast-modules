"""Krok A: numery koszulek ze starej bazy do WP (tools/import_wp/numery.py): dopasowanie, zasady bezpieczeństwa, tryb na sucho, zapis, powtórka, cofnięcie."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'import_wp'))
import logo  # noqa: E402
import numery  # noqa: E402
from atrapa_wp import AtrapaWp  # noqa: E402
from wp_rest import WpRest  # noqa: E402

ALFA, BETA, GAMMA = 101, 102, 103


def stara_baza(sciezka):
    c = sqlite3.connect(sciezka)
    c.executescript("""
        create table scrapers (id integer primary key, folder text);
        create table teams (id integer primary key, name text);
        create table team_foreign_ids (team_id integer, scraper_id integer, foreign_id text);
        create table players (id integer primary key, first_name text, last_name text, team_id integer, number integer);
        create table game_players (id integer primary key, player_id integer, number integer);
        insert into scrapers values (1, 'nalffutsal');
        insert into teams values (1, 'Alfa'), (2, 'Beta'), (3, 'Gamma');
        insert into team_foreign_ids values (1, 1, 'alfa'), (2, 1, 'beta'), (3, 1, 'gamma');
    """)
    zaw = [  # id, imię, nazwisko, drużyna, numer
        (1, 'Jan', 'Kowalski', 1, 7), (2, 'Adam', 'Nowak', 2, None), (3, 'Piotr', 'Zieliński', 1, 5), (4, 'Marek', 'Lis', 1, 5), (5, 'Tomasz', 'Kot', 1, 5),
        (6, 'Leon', 'Wrona', 1, 0), (7, 'Ignacy', 'Sowa', 1, 11), (8, 'Ewa', 'Jastrząb', 2, 8), (9, 'Jan', 'Bury', 2, 3), (10, 'Jan', 'Bury', 2, 4),
        (11, 'Rafał', 'Remis', 1, None), (12, 'Zbigniew', 'Stary', 1, 20), (13, 'Dawid', 'Dubel', 1, 15), (14, 'Wit', 'Wielki', 1, 21),
        (15, 'Mateusz', 'Max', 3, 99), (16, 'Michał', 'Min', 3, 1),
    ]
    c.executemany('insert into players values (?, ?, ?, ?, ?)', zaw)
    # Nowak bez numeru zawodnika: najczęstszy numer ze składów to 10; Remis: remis 4:5 -> numer niejednoznaczny
    c.executemany('insert into game_players (player_id, number) values (?, ?)', [(2, 10), (2, 10), (2, 12), (11, 4), (11, 5)])
    c.commit()
    c.close()


def wp_dane(a):
    for tid, nazwa, slug in ((ALFA, 'Alfa', 'alfa'), (BETA, 'Beta', 'beta'), (GAMMA, 'Gamma', 'gamma')):
        a.dane['teams'][tid] = {'id': tid, 'title': {'rendered': nazwa}, 'slug': slug, 'abbreviation': '', 'meta': {}}
    gracze = [  # id, tytuł, numer, aktualne drużyny
        (1, 'Kowalski Jan', '', [ALFA]), (2, 'Adam Nowak', '', [BETA]), (3, 'Zielinski Piotr', '9', [ALFA]), (4, 'Lis Marek', '', [ALFA]), (5, 'Kot Tomasz', '', [ALFA]),
        (6, 'Wrona Leon', '', [ALFA]), (7, 'Sowa Ignacy', '', [GAMMA]), (8, 'Jastrzab Ewa', '', [BETA]), (9, 'Bury Jan', '', [BETA]), (11, 'Remis Rafał', '', [ALFA]),
        (13, 'Dubel Dawid', '', [ALFA]), (23, 'Dubel Dawid', '', [ALFA]), (14, 'Wielki Wit', '', [ALFA, BETA]), (15, 'Max Mateusz', '', [GAMMA]),
        (16, 'Min Michał', '', [GAMMA]), (30, 'Orzeł Karol', '8', [BETA]), (31, 'Inny Ivan', '21', [BETA]),
    ]
    for pid, tytul, numer, druzyny in gracze:
        a.dane['players'][pid] = {'id': pid, 'title': {'rendered': tytul}, 'number': numer, 'current_teams': druzyny, 'teams': druzyny, 'meta': {}}


class NumeryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='bm-numery-'))
        self.baza = self.tmp / 'database.db'
        stara_baza(self.baza)
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        wp_dane(self.a)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')

    def _plan(self):
        stare_dr, stare_zaw = numery.wczytaj_stara_baze(self.baza, logo.SCRAPER_FOLDER['nalf'])
        return numery.zaplanuj(stare_dr, stare_zaw, logo.wczytaj_druzyny_wp(self.wp), numery.wczytaj_zawodnikow_wp(self.wp), 'nalf')

    def test_tokeny_ignoruja_kolejnosc_polskie_znaki_i_myslniki(self):
        self.assertEqual(numery.tokeny('Kędzior Grzegorz'), numery.tokeny('grzegorz KEDZIOR'))
        self.assertEqual(numery.tokeny('Chguig - Koziński Naimi'), numery.tokeny('Naimi Koziński Chguig'))

    def test_plan_zapisuje_tylko_zawodnikow_spelniajacych_wszystkie_zasady(self):
        plan = self._plan()
        zapis = {p['nazwa']: p['numer'] for p in plan['propozycje']}
        self.assertEqual(zapis, {'Kowalski Jan': 7, 'Adam Nowak': 10, 'Max Mateusz': 99, 'Min Michał': 1})
        by_name = {p['nazwa']: p for p in plan['propozycje']}
        self.assertEqual(by_name['Adam Nowak']['zrodlo_numeru'], 'najczęstszy numer ze składów meczowych')
        self.assertEqual(by_name['Kowalski Jan']['zrodlo_numeru'], 'numer zawodnika')
        self.assertTrue(all(p['etykieta'] == 'propozycja ze starej bazy' for p in plan['propozycje']))

    def test_pominiete_maja_powody(self):
        pom = self._plan()['pominiete']
        wszystko = {powod: ' | '.join(lista) for powod, lista in pom.items()}
        szukaj = lambda fragment: next(v for k, v in wszystko.items() if fragment in k)
        self.assertIn('Lis Marek', szukaj('ten sam numer proponowany'))
        self.assertIn('Kot Tomasz', szukaj('ten sam numer proponowany'))
        self.assertIn('Wrona Leon', szukaj('spoza zakresu'))
        self.assertIn('Sowa Ignacy', szukaj('inna drużyna'))
        self.assertIn('w drużynie „Alfa”', szukaj('inna drużyna'))                       # w opisie nazwa starej drużyny
        zajete = szukaj('numer zajęty')
        self.assertIn('Jastrzab Ewa', zajete)                                            # Beta ma już 8 (Orzeł Karol)
        self.assertIn('Wielki Wit', zajete)                                              # zawodnik w dwóch drużynach: numer zajęty w Becie
        self.assertIn('Bury Jan', szukaj('kilku zawodników o tej nazwie w starej bazie'))
        self.assertIn('Dubel Dawid', szukaj('kilku zawodników WP'))
        self.assertIn('Remis Rafał', szukaj('brak numeru'))

    def test_numer_w_wp_nigdy_nie_jest_zmieniany_a_roznica_trafia_do_informacji(self):
        plan = self._plan()
        self.assertTrue(any('Zielinski Piotr' in x and 'w WP 9' in x and 'stara baza 5' in x for x in plan['rozne_od_wp']))
        self.assertNotIn('Zielinski Piotr', [p['nazwa'] for p in plan['propozycje']])

    def test_liczniki_i_stare_numery_bez_odpowiednika(self):
        c = self._plan()['liczniki']
        self.assertEqual(c['do_zapisu'], 4)
        self.assertGreaterEqual(c['stare_z_numerem_bez_odpowiednika_w_wp'], 1)             # Stary Zbigniew (20), Bury Jan (drugi) itd.

    def test_na_sucho_niczego_nie_wysyla(self):
        plan = self._plan()
        self.a.wyzeruj_zapytania()
        wyniki = numery.zapisz(self.wp, plan, na_sucho=True)
        self.assertEqual(len(wyniki['zapisane']), 4)
        self.assertEqual(self.a.posty(), [])
        self.assertEqual(self.a.dane['players'][1]['number'], '')

    def test_zapis_wpisuje_numery_a_powtorka_nie_zapisuje_niczego(self):
        wyniki = numery.zapisz(self.wp, self._plan(), na_sucho=False)
        self.assertEqual(len(wyniki['zapisane']), 4)
        self.assertEqual((self.a.dane['players'][1]['number'], self.a.dane['players'][2]['number']), (7, 10))
        self.assertEqual(self.a.dane['players'][3]['number'], '9')                           # nietknięty
        self.a.wyzeruj_zapytania()
        drugi = self._plan()
        self.assertEqual(drugi['propozycje'], [])                                           # numery są już w WP: nic do zapisu
        self.assertEqual(numery.zapisz(self.wp, drugi, na_sucho=False)['zapisane'], [])
        self.assertEqual(self.a.posty(), [])

    def test_numer_ktory_pojawil_sie_w_miedzyczasie_nie_jest_nadpisany(self):
        plan = self._plan()
        self.a.dane['players'][1]['number'] = '33'                                          # ktoś wpisał numer po wyliczeniu planu
        wyniki = numery.zapisz(self.wp, plan, na_sucho=False)
        self.assertEqual(self.a.dane['players'][1]['number'], '33')
        self.assertTrue(any('Kowalski Jan' in x for x in wyniki['zmienione_w_miedzyczasie']))
        self.assertEqual(len(wyniki['zapisane']), 3)

    def test_cofnij_usuwa_tylko_numery_niezmienione_od_zapisu(self):
        plan = self._plan()
        wyniki = numery.zapisz(self.wp, plan, na_sucho=False)
        plik = self.tmp / 'raport.json'
        plik.write_text(json.dumps({'zapisane': wyniki['zapisane']}), encoding='utf-8')
        self.a.dane['players'][2]['number'] = 11                                            # po zapisie ktoś zmienił numer Nowaka
        na_sucho = numery.cofnij(self.wp, plik, na_sucho=True)
        self.assertEqual(len(na_sucho['usuniete']), 3)
        self.assertEqual(self.a.dane['players'][1]['number'], 7)                            # na sucho nic nie usunięto
        wynik = numery.cofnij(self.wp, plik, na_sucho=False)
        self.assertEqual(sorted(p['nazwa'] for p in wynik['usuniete']), ['Kowalski Jan', 'Max Mateusz', 'Min Michał'])
        self.assertEqual((self.a.dane['players'][1]['number'], self.a.dane['players'][15]['number']), ('', ''))
        self.assertEqual(self.a.dane['players'][2]['number'], 11)                            # zmieniony później: zostaje
        self.assertTrue(any('Adam Nowak' in x for x in wynik['zmienione_pozniej']))

    def test_raport_oznacza_kazdy_zapisany_numer_jako_propozycje_ze_starej_bazy(self):
        plan = self._plan()
        tekst = numery.raport('nalf', plan, numery.zapisz(self.wp, plan, na_sucho=True), na_sucho=True)
        wiersze = [l for l in tekst.splitlines() if l.startswith('    - ') and ': nr ' in l]
        self.assertEqual(len(wiersze), 4)
        self.assertTrue(all('propozycja ze starej bazy' in l for l in wiersze))
        self.assertIn('NA SUCHO', tekst)
        self.assertIn('pominięte: ten sam numer proponowany', tekst)

    def test_stara_baza_jest_tylko_czytana(self):
        przed = hashlib.sha256(self.baza.read_bytes()).hexdigest()
        self._plan()
        self.assertEqual(hashlib.sha256(self.baza.read_bytes()).hexdigest(), przed)
        con = sqlite3.connect(f'file:{self.baza.as_posix()}?mode=ro', uri=True)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute('insert into scrapers values (9, "x")')                              # tak otwiera ją narzędzie: zapis niemożliwy
        con.close()

    def test_numer_niejednoznaczny_ze_skladow_to_brak_numeru(self):
        _, zaw = numery.wczytaj_stara_baze(self.baza, 'nalffutsal')
        remis = next(z for z in zaw if z['nazwa'] == 'Remis Rafał')
        self.assertIsNone(remis['numer'])
        self.assertTrue(remis['ma_skladowe'])


if __name__ == '__main__':
    unittest.main()
