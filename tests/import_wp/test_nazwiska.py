"""Etap W7-0: imię i nazwisko zawodnika jako osobne pola w WP (bm_first_name, bm_last_name) i raport nazwisk niepewnych."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_import_nalf as tn  # noqa: E402
import test_import_superscore as ts  # noqa: E402
import importuj  # noqa: E402
import nalf  # noqa: E402
from atrapa_wp import AtrapaWp  # noqa: E402
from nazwy import podziel_nazwisko_imie  # noqa: E402
from wp_rest import WpRest  # noqa: E402


class PodzialTests(unittest.TestCase):
    def test_dwa_wyrazy_to_pewny_podzial_nazwisko_imie(self):
        self.assertEqual(podziel_nazwisko_imie('Kędzior Grzegorz'), ('Kędzior', 'Grzegorz', True))

    def test_nazwisko_wieloczlonowe_i_jeden_wyraz_sa_niepewne(self):
        self.assertEqual(podziel_nazwisko_imie('Van Dijk Jan'), ('Van Dijk', 'Jan', False))
        self.assertEqual(podziel_nazwisko_imie('Kowalski Jan Maria'), ('Kowalski Jan', 'Maria', False))      # zgadnięte: do ręcznej poprawki
        self.assertEqual(podziel_nazwisko_imie('Pele'), ('Pele', '', False))
        self.assertEqual(podziel_nazwisko_imie('  '), ('', '', False))

    def test_encje_html_w_nazwie_sa_zamieniane(self):
        self.assertEqual(podziel_nazwisko_imie("O&#8217;Brien&nbsp;Sean"), ('O’Brien', 'Sean', True))


class ZrodlaTests(unittest.TestCase):
    def test_nalf_zawodnik_dostaje_podzial_i_znacznik_niepewnosci(self):
        d = nalf.norm_zawodnik({'id': 1, 'title': {'rendered': 'Van Dijk Jan'}, 'slug': 'x', 'number': '7', 'teams': [], 'leagues': [], 'seasons': []})
        self.assertEqual((d['last_name'], d['first_name'], d['name_uncertain']), ('Van Dijk', 'Jan', True))
        d = nalf.norm_zawodnik({'id': 2, 'title': {'rendered': 'Kędzior Grzegorz'}, 'teams': [], 'leagues': [], 'seasons': []})
        self.assertEqual((d['last_name'], d['first_name'], d['name_uncertain']), ('Kędzior', 'Grzegorz', False))

    def test_superscore_dzieli_dokladnie_po_przecinku_nawet_dla_wieloczlonowych(self):
        d = ts.superscore.norm_zawodnik({'player': {'id': 'p1', 'name': 'Van der Berg, Jan Maria', 'seo_id': {}}, 'shirt_number': '3'}, 'T', 'L', 'S')
        self.assertEqual((d['last_name'], d['first_name'], d['name_uncertain']), ('Van der Berg', 'Jan Maria', False))
        self.assertEqual(d['name'], 'Van der Berg Jan Maria')
        d = ts.superscore.norm_zawodnik({'player': {'id': 'p2', 'name': 'Bez Przecinka Nikt', 'seo_id': {}}}, 'T', 'L', 'S')
        self.assertTrue(d['name_uncertain'])                                             # brak przecinka: heurystyka i znacznik


class ImportNazwiskTests(unittest.TestCase):
    def setUp(self):
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')

    def _importuj(self, dane, zrodlo='nalf'):
        return importuj.importuj_zrodlo(self.wp, zrodlo, dane, log=lambda *x: None)

    def _dane_z_wieloczlonowym(self):
        d = tn.dane_zrodla()
        p = d['zawodnicy'][0]
        p['name'] = 'Van Dijk Jan'
        p['last_name'], p['first_name'], p['name_uncertain'] = 'Van Dijk', 'Jan', True
        return d, p

    def test_import_zapisuje_osobne_pola_imienia_i_nazwiska(self):
        d = tn.dane_zrodla()
        self._importuj(d)
        p = d['zawodnicy'][0]
        rekord = self.a.po_zrodle('players', p['id'])
        self.assertEqual((rekord['meta']['bm_last_name'], rekord['meta']['bm_first_name']), (p['last_name'], p['first_name']))

    def test_raport_wypisuje_niepewne_nazwiska(self):
        d, p = self._dane_z_wieloczlonowym()
        imp = self._importuj(d)
        self.assertEqual(len(imp.niepewne_nazwiska), 1)
        self.assertIn('Van Dijk Jan', imp.niepewne_nazwiska[0])
        txt = importuj.raport(imp, False)
        self.assertIn('NAZWISKA NIEPEWNE (1)', txt)
        self.assertIn('bm_last_name', txt)

    def test_reczna_poprawka_w_wp_przezywa_aktualizacje_rekordu_i_znika_z_raportu(self):
        d, p = self._dane_z_wieloczlonowym()
        self._importuj(d)
        rekord = self.a.po_zrodle('players', p['id'])
        rekord['meta']['bm_last_name'], rekord['meta']['bm_first_name'] = 'Van', 'Dijk Jan'          # właściciel poprawił w panelu WP
        d2 = copy.deepcopy(d)
        next(x for x in d2['zawodnicy'] if x['id'] == p['id'])['number'] = 99                         # źródło zmieniło numer: rekord aktualizowany
        imp = self._importuj(d2)
        self.assertEqual(imp.liczniki['zawodnicy'].zmienione, 1)
        self.assertEqual((rekord['meta']['bm_last_name'], rekord['meta']['bm_first_name']), ('Van', 'Dijk Jan'))   # import nie nadpisał poprawki
        self.assertEqual(rekord['number'], 99)
        self.assertEqual(imp.niepewne_nazwiska, [])                                                    # poprawiony nie jest już zgłaszany

    def test_zmiana_nazwy_w_zrodle_nadpisuje_pola_imienia_i_nazwiska(self):
        d, p = self._dane_z_wieloczlonowym()
        self._importuj(d)
        d2 = copy.deepcopy(d)
        x = next(x for x in d2['zawodnicy'] if x['id'] == p['id'])
        x['name'], x['last_name'], x['first_name'], x['name_uncertain'] = 'Kowalski Adam', 'Kowalski', 'Adam', False
        self._importuj(d2)
        rekord = self.a.po_zrodle('players', p['id'])
        self.assertEqual((rekord['meta']['bm_last_name'], rekord['meta']['bm_first_name']), ('Kowalski', 'Adam'))

    def test_istniejacy_zawodnik_bez_pol_imienia_dostaje_je_przy_nastepnym_imporcie(self):
        d = tn.dane_zrodla()
        self._importuj(d)
        p = d['zawodnicy'][0]
        rekord = self.a.po_zrodle('players', p['id'])
        rekord['meta'].pop('bm_last_name')
        rekord['meta'].pop('bm_first_name')                                                            # tak wyglądał rekord sprzed W7-0
        rekord['meta']['bm_source_hash'] = 'stary-skrot'
        imp = self._importuj(d)
        self.assertEqual(imp.liczniki['zawodnicy'].zmienione, 1)
        self.assertEqual(rekord['meta']['bm_last_name'], p['last_name'])

    def test_superscore_nie_ma_niepewnych_nazwisk(self):
        imp = self._importuj(ts.dane(), 'superscore')
        self.assertEqual(imp.niepewne_nazwiska, [])
        rekord = [o for o in self.a.dane['players'].values() if o['title'].startswith('Bargie')][0]
        self.assertEqual((rekord['meta']['bm_last_name'], rekord['meta']['bm_first_name']), ('Bargieł', 'Bartosz'))


if __name__ == '__main__':
    unittest.main()
