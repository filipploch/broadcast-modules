"""Etap I3: raport zgodności importu (tools/import_wp/porownaj.py) na atrapie WP i fixturach źródeł."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_import_nalf as tn  # noqa: E402  (fixtury i atrapa źródła NALF)
import test_import_superscore as ts  # noqa: E402
import importuj  # noqa: E402
import porownaj  # noqa: E402
from atrapa_wp import AtrapaWp  # noqa: E402
from wp_rest import WpRest  # noqa: E402


class TabelaTests(unittest.TestCase):
    def test_tabela_z_wynikow_i_kolejnosc(self):
        t = porownaj.tabela([('A', 'B', 2, 1), ('B', 'C', 0, 0), ('C', 'A', 1, 3)])
        self.assertEqual(t['A'], {'m': 2, 'pkt': 6, 'gz': 5, 'gs': 2})
        self.assertEqual(t['B'], {'m': 2, 'pkt': 1, 'gz': 1, 'gs': 2})
        self.assertEqual(t['C'], {'m': 2, 'pkt': 1, 'gz': 1, 'gs': 3})
        self.assertEqual(porownaj.kolejnosc(t), ['A', 'B', 'C'])           # remis punktów: lepsza różnica bramek

    def test_mecz_z_pustym_wynikiem_zrodla_jest_nierozegrany(self):
        self.assertFalse(porownaj.rozegrany_w_zrodle({'teams': [1, 2], 'results': {'1': {'goals': ''}, '2': {'goals': ''}}}))
        self.assertTrue(porownaj.rozegrany_w_zrodle({'teams': [1, 2], 'results': {'1': {'goals': '0'}, '2': {'goals': '3'}}}))


class RaportNalfTests(unittest.TestCase):
    def setUp(self):
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')
        self.dane = tn.dane_zrodla()
        importuj.importuj_zrodlo(self.wp, 'nalf', self.dane, log=lambda *x: None)

    def _raport(self, dane=None, tabele=None):
        return porownaj.porownaj(dane or self.dane, porownaj.wczytaj_wp(self.wp, 'nalf'), tabele)

    def test_po_imporcie_wszystko_jest_zgodne(self):
        r = self._raport()
        self.assertEqual(r['rozbieznosci'], [])
        self.assertEqual({l['liga'] for l in r['ligi']}, {'Dywizja A', 'Dywizja B', 'Puchar Ligi'})
        for l in r['ligi']:
            for k in ('druzyny', 'zawodnicy', 'mecze', 'rozegrane', 'przyszle', 'bramki'):
                self.assertEqual(l[k][0], l[k][1], f'{l["liga"]} {k}')
        self.assertEqual(sum(l['mecze'][0] for l in r['ligi']), 3)
        self.assertEqual(len(r['probka']), 1)                              # fixtura ma jeden mecz rozegrany

    def test_zmieniony_wynik_w_wp_jest_wykryty(self):
        mecz = self.a.po_zrodle('events', tn.ROZEGRANY)
        wp_dr = str(next(iter(mecz['results'])))
        mecz['results'][wp_dr]['goals'] = '7'
        roz = self._raport()['rozbieznosci']
        self.assertTrue(any(f'mecz {tn.ROZEGRANY}: wynik' in r for r in roz), roz)
        self.assertTrue(any('bramki' in r or 'tabela z wyników' in r for r in roz), roz)

    def test_brakujacy_mecz_i_zla_data_sa_wykryte(self):
        przyszly = self.a.po_zrodle('events', tn.PRZYSZLY)
        przyszly['date'] = '2030-01-01T00:00:00'
        usuniety = self.a.po_zrodle('events', tn.PUCHAROWY)
        del self.a.dane['events'][usuniety['id']]
        roz = self._raport()['rozbieznosci']
        self.assertTrue(any(f'mecz {tn.PRZYSZLY}: data' in r for r in roz), roz)
        self.assertTrue(any(f'mecz {tn.PUCHAROWY} jest w źródle, brak w WP' in r for r in roz), roz)

    def test_tabela_zrodla_zgodna_i_niezgodna(self):
        r0 = self._raport()
        dane = self.dane
        mecz = next(m for m in dane['mecze'] if m['id'] == tn.ROZEGRANY)
        lid = str(mecz['leagues'][0])
        g, a = (str(t) for t in mecz['teams'])
        gg, ga = int(mecz['results'][g]['goals']), int(mecz['results'][a]['goals'])
        dobra = {lid: {g: {'pkt': 3 if gg > ga else 0, 'm': 1, 'gz': gg, 'gs': ga, 'pos': 1}, a: {'pkt': 0 if gg > ga else 3, 'm': 1, 'gz': ga, 'gs': gg, 'pos': 2}}}
        self.assertEqual(self._raport(tabele=dobra)['rozbieznosci'], r0['rozbieznosci'])
        zla = {lid: {g: {**dobra[lid][g], 'pkt': 99}}}
        self.assertTrue(any('tabela źródła' in r for r in self._raport(tabele=zla)['rozbieznosci']))

    def test_raport_tekstowy_ma_sekcje_i_wynik(self):
        txt = porownaj.raport_tekstowy('nalf', self._raport(), '0 nowych i 0 zmienionych rekordów (OK)')
        for fragment in ('Raport zgodności importu nalf', '== Dywizja A', 'mecze rozegrane', 'Próbka meczów', 'Powtarzalność', 'WYNIK: ZGODNE'):
            self.assertIn(fragment, txt)


class RaportSuperscoreTests(unittest.TestCase):
    def setUp(self):
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')
        self.dane = ts.dane()
        importuj.importuj_zrodlo(self.wp, 'superscore', self.dane, log=lambda *x: None)
        self.tmp = Path(tempfile.mkdtemp(prefix='bm-por-'))

    def _stara_baza(self, wyniki):
        """Minimalna kopia bazy modułu: drużyny z identyfikatorem Superscore i mecze zakończone. wyniki: [(hash gospodarza, hash gościa, g, a)]."""
        plik = self.tmp / 'database.db'
        con = sqlite3.connect(plik)
        con.executescript("create table scrapers(id integer primary key, folder text);"
                          "create table team_foreign_ids(team_id integer, scraper_id integer, foreign_id text);"
                          "create table games(home_team_id integer, away_team_id integer, home_team_goals integer, away_team_goals integer, status integer);"
                          "insert into scrapers values (3, 'superscore');")
        hasze = sorted({h for w in wyniki for h in w[:2]})
        for i, h in enumerate(hasze, 1):
            con.execute('insert into team_foreign_ids values (?, 3, ?)', (i, f'slug-{h}/{h}'))
        for g, a, gg, ga in wyniki:
            con.execute('insert into games values (?, ?, ?, ?, 2)', (hasze.index(g) + 1, hasze.index(a) + 1, gg, ga))
        con.commit()
        con.close()
        return plik

    def _raport(self, stara=None):
        return porownaj.porownaj(self.dane, porownaj.wczytaj_wp(self.wp, 'superscore'), None, stara)

    def test_po_imporcie_zgodne(self):
        self.assertEqual(self._raport()['rozbieznosci'], [])

    def test_wyniki_ze_starej_bazy_zgodne_i_niezgodne(self):
        m = next(x for x in self.dane['mecze'] if x['id'] == ts.ZAKONCZONY)
        g, a = m['teams']
        zgodna = self._stara_baza([(g, a, int(m['results'][g]['goals']), int(m['results'][a]['goals']))])
        r = self._raport(zgodna)
        self.assertEqual(r['rozbieznosci'], [])
        self.assertTrue(any('zgodnych z WP 1' in i for i in r['info']))
        (self.tmp / 'database.db').unlink()
        niezgodna = self._stara_baza([(g, a, 9, 9)])
        self.assertTrue(any('stara baza kontra WP' in x for x in self._raport(niezgodna)['rozbieznosci']))

    def test_mecz_rozegrany_w_zrodlu_a_bez_wyniku_w_wp_to_rozbieznosc_z_podpowiedzia_o_imporcie(self):
        mecz = self.a.po_zrodle('events', ts.ZAKONCZONY)
        mecz.pop('results')                                                  # tak wyglądałby WP sprzed rozegrania meczu
        roz = self._raport()['rozbieznosci']
        self.assertTrue(any('rozegrane' in r for r in roz), roz)


if __name__ == '__main__':
    unittest.main()
