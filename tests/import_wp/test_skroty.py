"""Etap W7-0b: skrót 3-znakowy drużyny (bm_short_name): algorytm wyliczania i kolejność źródeł."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'import_wp'))
import importuj  # noqa: E402
import logo  # noqa: E402
import test_import_superscore as ts  # noqa: E402
import skroty  # noqa: E402
from atrapa_wp import AtrapaWp  # noqa: E402
from wp_rest import WpRest  # noqa: E402


class AlgorytmTests(unittest.TestCase):
    def test_pierwsze_trzy_litery_pierwszego_slowa_bez_formy_prawnej_i_polskich_znakow(self):
        self.assertEqual(skroty.wylicz_skrot('Garbarnia Kraków'), 'GAR')
        self.assertEqual(skroty.wylicz_skrot('KS Łagiewniki'), 'LAG')
        self.assertEqual(skroty.wylicz_skrot('Żurawie'), 'ZUR')

    def test_krotkie_nazwy_dopelniane_inicjalami_kolejnych_slow(self):
        self.assertEqual(skroty.wylicz_skrot('NO NAME NO GAME!'), 'NON')
        self.assertEqual(skroty.wylicz_skrot('16 Batalion'), '16B')
        self.assertEqual(skroty.wylicz_skrot('K2'), 'K2')

    def test_kolizje_sa_rozwiazywane_i_oznaczane(self):
        w = skroty.wylicz_unikalne({1: 'Kabel Kraków', 2: 'Kabel Nowy'})
        self.assertEqual(len({v[0] for v in w.values()}), 2)
        self.assertTrue(any(v[1] for v in w.values()))

    def test_zajete_skroty_sa_omijane(self):
        w = skroty.wylicz_unikalne({1: 'Garbarnia'}, zajete=['GAR'])
        self.assertNotEqual(w[1][0], 'GAR')
        self.assertTrue(w[1][1])


class UstalSkrotyTests(unittest.TestCase):
    def _w(self, i, nazwa, abbr='', skrot=''):
        return {'id': i, 'nazwa': nazwa, 'abbr': abbr, 'skrot': skrot}

    def test_kolejnosc_zrodel_istniejacy_api_stara_baza_wyliczony(self):
        druzyny = [self._w(1, 'Ręczna', skrot='RRR'), self._w(2, 'Z API', abbr='zap'), self._w(3, 'Stara Baza'),
                   self._w(4, 'Nowa Drużyna')]
        pary = [(druzyny[2], {'skrot': 'ŻAR'}, 'po nazwie')]
        wynik, powt = logo.ustal_skroty(druzyny, pary)
        self.assertNotIn(1, wynik)                                  # ręczna wartość nietknięta
        self.assertEqual(wynik[2][:2], ('ZAP', 'API/skrót w WP'))
        self.assertEqual(wynik[3][:2], ('ŻAR', 'stara baza'))      # bez zmian, także z polskimi znakami
        self.assertEqual(wynik[4][:2], ('NOW', 'wyliczony z nazwy'))
        self.assertEqual(powt, [])

    def test_powtorzone_stale_skroty_sa_zglaszane(self):
        druzyny = [self._w(1, 'A', skrot='AAA'), self._w(2, 'B', skrot='AAA')]
        _, powt = logo.ustal_skroty(druzyny, [])
        self.assertEqual(powt, ['AAA'])


class ZapisSkrotowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='bm-skroty-'))
        (self.tmp / 'logos').mkdir()
        baza = self.tmp / 'database.db'
        con = sqlite3.connect(baza)
        con.executescript("""
            create table scrapers(id integer primary key, folder text);
            create table teams(id integer primary key, name text, name_14 text, logo_path text, short_name text);
            create table team_foreign_ids(team_id integer, scraper_id integer, foreign_id text);
            insert into scrapers values (3, 'superscore');
            insert into teams values (1, 'Żarówki', 'Żarówki', 'x.png', 'ŻAR');
            insert into team_foreign_ids values (1, 3, 'z/zar00001');
        """)
        con.commit()
        con.close()
        self.baza = baza
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')
        for sid, nazwa in (('zar00001', 'Żarówki'), ('nowa0001', 'Nowa Drużyna')):
            self.wp.utworz('sportspress/v2/teams', {'title': nazwa, 'slug': nazwa.lower().replace(' ', '-'),
                                                   'meta': {'bm_source': 'superscore', 'bm_source_id': sid}})

    def _uruchom(self, na_sucho=False):
        stare = logo.mapa_ze_starej_bazy(self.baza, 'superscore')
        wp_dr = logo.wczytaj_druzyny_wp(self.wp)
        pary, _, _ = logo.dopasuj(stare, wp_dr, 'garbarnia')
        skroty_wp, powt = logo.ustal_skroty(wp_dr, pary)
        r = logo.zastosuj(self.wp, pary, self.tmp / 'logos', na_sucho=na_sucho, skroty_wp=skroty_wp)
        return wp_dr, skroty_wp, powt, r

    def test_zapis_skrotow_ze_starej_bazy_i_wyliczonych_oraz_powtorka_bez_zmian(self):
        self._uruchom()
        self.assertEqual(self.a.po_zrodle('teams', 'zar00001')['meta']['bm_short_name'], 'ŻAR')
        self.assertEqual(self.a.po_zrodle('teams', 'nowa0001')['meta']['bm_short_name'], 'NOW')
        self.a.wyzeruj_zapytania()
        _, skroty_wp, _, r = self._uruchom()
        self.assertEqual((skroty_wp, r['zapisane'], self.a.posty()), ({}, 0, []))

    def test_na_sucho_niczego_nie_zapisuje_a_raport_wymienia_wyliczone(self):
        wp_dr, skroty_wp, powt, _ = self._uruchom(na_sucho=True)
        self.assertNotIn('bm_short_name', self.a.po_zrodle('teams', 'nowa0001')['meta'])
        txt = logo.raport_skrotow(wp_dr, skroty_wp, powt)
        self.assertIn('DO SPRAWDZENIA', txt)
        self.assertIn('Nowa Drużyna -> NOW', txt)


class ImportSkrotuTests(unittest.TestCase):
    def setUp(self):
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')

    def _importuj(self, dane):
        return importuj.importuj_zrodlo(self.wp, 'superscore', dane, log=lambda *x: None)

    def test_skrot_z_superscore_trafia_do_bm_short_name_a_reczna_poprawka_zostaje(self):
        d = ts.dane()
        self._importuj(d)
        rekord = self.a.po_zrodle('teams', ts.ORZEL)
        self.assertEqual(rekord['meta']['bm_short_name'], 'ORZ')
        rekord['meta']['bm_short_name'] = 'OMY'                                      # właściciel poprawił w panelu WP
        next(t for t in d['druzyny'] if t['id'] == ts.ORZEL)['name'] = 'Orzel Myslenice 2'   # źródło zmieniło nazwę: rekord aktualizowany
        self._importuj(d)
        self.assertEqual(rekord['meta']['bm_short_name'], 'OMY')


if __name__ == '__main__':
    unittest.main()
