"""Etap I4: loga i nazwy 14-znakowe drużyn do WP (tools/import_wp/logo.py): mapa ze starej bazy, dopasowanie, dopasowanie po nazwie pliku."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'import_wp'))
import logo  # noqa: E402
from atrapa_wp import AtrapaWp  # noqa: E402
from wp_rest import WpRest  # noqa: E402


class FunkcjeTests(unittest.TestCase):
    def test_plik_logo_normalizuje_rozne_zapisy_sciezki(self):
        self.assertEqual(logo.plik_logo('/static//images/logos/garbarnia/Garbarnia.png'), 'garbarnia/Garbarnia.png')
        self.assertEqual(logo.plik_logo('static/images/logos/futsal_nalf/16Batalion.png'), 'futsal_nalf/16Batalion.png')
        self.assertEqual(logo.plik_logo('/static/////////images/logos/garbarnia/luban.png'), 'garbarnia/luban.png')
        self.assertEqual(logo.plik_logo('static/images/logos/garbarnia/05 - kmita zabierzow.png'), 'garbarnia/05 - kmita zabierzow.png')
        self.assertIsNone(logo.plik_logo('static/images/logos/default.png'))
        self.assertIsNone(logo.plik_logo('/static/images/logos/default.png'))
        self.assertIsNone(logo.plik_logo(None))
        self.assertIsNone(logo.plik_logo(''))

    def test_normalizacja_nazw_polskie_znaki_i_wielkosc_liter(self):
        self.assertEqual(logo.normalizuj('Orzeł Myślenice'), 'orzel myslenice')
        self.assertEqual(logo.normalizuj('KS Chełmek'), logo.normalizuj('KS Chelmek'))
        self.assertEqual(logo.normalizuj('Wr&#243;blowianka   Krak&#243;w'), 'wroblowianka krakow')


class DopasowaniePlikowTests(unittest.TestCase):
    PLIKI = ['garbarnia/TempoBialka.png', 'garbarnia/Bobrek.png', 'garbarnia/Kmita.png', 'garbarnia/Orzel.png', 'garbarnia/OrzelMyslenice.png',
             'garbarnia/10 - wroblowianka.png', 'garbarnia/SokolKocmyrzow.png', 'garbarnia/luban.png']

    def _dopasuj(self, druzyny, pliki=None):
        return logo.dopasuj_pliki_po_nazwie(druzyny, pliki or self.PLIKI)

    def test_zgodnosc_dokladna_prefiks_i_slowo_w_nazwie(self):
        wynik = self._dopasuj([(1, 'Tempo Białka'), (2, 'LKS Bobrek'), (3, 'AP Kmita Zabierzów'), (4, 'Sokół Kocmyrzów Baranówka'),
                               (5, 'Wróblowianka Kraków')])
        self.assertEqual(wynik, {1: 'garbarnia/TempoBialka.png', 2: 'garbarnia/Bobrek.png', 3: 'garbarnia/Kmita.png',
                                 4: 'garbarnia/SokolKocmyrzow.png', 5: 'garbarnia/10 - wroblowianka.png'})            # numer porządkowy w nazwie pliku pomijany

    def test_dokladna_zgodnosc_wygrywa_z_prefiksem_i_plik_nie_idzie_do_obcej_druzyny(self):
        wynik = self._dopasuj([(1, 'Orzeł Myślenice')])
        self.assertEqual(wynik, {1: 'garbarnia/OrzelMyslenice.png'})           # „Orzel.png” jest prefiksem, ale dokładna zgodność ma pierwszeństwo
        self.assertNotIn(1, self._dopasuj([(1, 'Orzeł Ryczów'), (2, 'Orzeł Myślenice')], ['garbarnia/Orzel.png']))      # niejednoznaczne

    def test_nic_nie_pasuje_albo_za_krotki_trzon(self):
        self.assertEqual(self._dopasuj([(1, 'Zupełnie Inna Drużyna')]), {})
        self.assertEqual(self._dopasuj([(1, 'KS Ab Cd')], ['garbarnia/ab.png']), {})                             # trzon krótszy niż 5 znaków

    def test_ten_sam_plik_dla_dwoch_druzyn_to_brak_dopasowania(self):
        self.assertEqual(self._dopasuj([(1, 'Orzeł Ryczów'), (2, 'Orzeł Myślenice')], ['garbarnia/Orzel.png']), {})


class StaraBazaITestWpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='bm-logo-'))
        self.logos = self.tmp / 'logos'
        (self.logos / 'garbarnia').mkdir(parents=True)
        for f in ('Garbarnia.png', 'Kabel.png', 'TempoBialka.png'):
            (self.logos / 'garbarnia' / f).write_bytes(b'png')
        baza = self.tmp / 'database.db'
        con = sqlite3.connect(baza)
        con.executescript("""
            create table scrapers(id integer primary key, folder text);
            create table teams(id integer primary key, name text, name_14 text, logo_path text, short_name text default '');
            create table team_foreign_ids(team_id integer, scraper_id integer, foreign_id text);
            insert into scrapers values (3, 'superscore'), (1, 'nalffutsal');
            insert into teams(id, name, name_14, logo_path) values (1, 'Garbarnia Kraków', 'Garbarnia', '/static//images/logos/garbarnia/Garbarnia.png'),
                                     (2, 'Kabel Krakow', 'Kabel Krakow', 'static/images/logos/garbarnia/Kabel.png'),
                                     (3, 'Tempo Białka', 'Tempo Białka', 'static/images/logos/default.png'),
                                     (4, 'Drużyna Z Ogromną Nazwą', 'Dłuższa niż czternaście', 'static/images/logos/garbarnia/NieMaTegoPliku.png'),
                                     (5, 'Stara Drużyna', 'Stara', 'static/images/logos/garbarnia/Garbarnia.png');
            insert into team_foreign_ids values (1, 3, 'garbarnia-krakow/1536cfmu'), (2, 3, 'kabel-krakow/leea26wi'), (4, 3, 'ogromna/ogr12345');
        """)
        con.commit()
        con.close()
        self.baza = baza
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')
        for sid, nazwa in (('1536cfmu', 'Garbarnia Kraków'), ('leea26wi', 'Kabel Krakow'), ('ogr12345', 'Drużyna Z Ogromną Nazwą'), ('brak0000', 'Tempo Białka')):
            self.wp.utworz('sportspress/v2/teams', {'title': nazwa, 'slug': nazwa.lower().replace(' ', '-'),
                                                   'meta': {'bm_source': 'superscore', 'bm_source_id': sid}})

    def _uruchom(self, na_sucho=False):
        stare = logo.mapa_ze_starej_bazy(self.baza, 'superscore')
        wp_dr = logo.wczytaj_druzyny_wp(self.wp)
        pary, bez_wp, bez_stare = logo.dopasuj(stare, wp_dr, 'garbarnia')
        wolne = sorted(f'garbarnia/{p.name}' for p in (self.logos / 'garbarnia').glob('*'))
        return pary, bez_wp, bez_stare, logo.zastosuj(self.wp, pary, self.logos, na_sucho=na_sucho, wolne_pliki=wolne)

    def test_mapa_ze_starej_bazy_klucz_to_hash_a_domyslne_logo_to_none(self):
        stare = {s['nazwa']: s for s in logo.mapa_ze_starej_bazy(self.baza, 'superscore')}
        self.assertEqual(stare['Garbarnia Kraków']['klucz'], '1536cfmu')
        self.assertEqual(stare['Garbarnia Kraków']['logo'], 'garbarnia/Garbarnia.png')
        self.assertIsNone(stare['Tempo Białka']['logo'])
        self.assertIsNone(stare['Tempo Białka']['klucz'])

    def test_dopasowanie_po_identyfikatorze_potem_po_nazwie_i_zapis_pol(self):
        pary, bez_wp, bez_stare, r = self._uruchom()
        jak = {w['nazwa']: j for w, s, j in pary}
        self.assertEqual(jak, {'Garbarnia Kraków': 'po identyfikatorze', 'Kabel Krakow': 'po identyfikatorze', 'Drużyna Z Ogromną Nazwą': 'po identyfikatorze',
                               'Tempo Białka': 'po nazwie'})
        self.assertEqual([s['nazwa'] for s in bez_stare], ['Stara Drużyna'])
        garb = self.a.po_zrodle('teams', '1536cfmu')
        self.assertEqual((garb['meta']['bm_logo'], garb['meta']['bm_name14']), ('garbarnia/Garbarnia.png', 'Garbarnia'))
        tempo = self.a.po_zrodle('teams', 'brak0000')
        self.assertEqual(tempo['meta']['bm_logo'], 'garbarnia/TempoBialka.png')                    # z nazwy pliku (stara baza miała logo domyślne)
        self.assertIn('Tempo Białka <- garbarnia/TempoBialka.png', r['z_nazwy_pliku'])

    def test_brakujacy_plik_i_za_dluga_nazwa_14_sa_zglaszane_i_nie_zapisywane(self):
        _, _, _, r = self._uruchom()
        ogromna = self.a.po_zrodle('teams', 'ogr12345')
        self.assertNotIn('bm_logo', ogromna['meta'])
        self.assertNotIn('bm_name14', ogromna['meta'])
        self.assertTrue(any('NieMaTegoPliku.png' in x for x in r['brak_pliku']))
        self.assertTrue(any('Dłuższa niż czternaście' in x for x in r['name14_za_dlugie']))

    def test_powtorzenie_nie_wysyla_niczego_a_na_sucho_nie_zapisuje(self):
        self._uruchom(na_sucho=True)
        self.assertEqual([z for z in self.a.zapytania if z[0] == 'POST' and z[2] and 'meta' in z[2] and 'bm_logo' in z[2]['meta']], [])
        self._uruchom()
        self.a.wyzeruj_zapytania()
        _, _, _, r = self._uruchom()
        self.assertEqual((r['zapisane'], self.a.posty()), (0, []))

    def test_ten_sam_plik_dla_dwoch_druzyn_z_niepasujaca_nazwa_pliku_jest_poprawiany_z_nazwy_pliku(self):
        (self.logos / 'garbarnia' / 'Hattrick.png').write_bytes(b'png')
        (self.logos / 'garbarnia' / 'DRUGony.png').write_bytes(b'png')
        con = sqlite3.connect(self.baza)
        con.executescript("insert into teams(id, name, name_14, logo_path) values (10, 'DRUGony', 'DRUGony', 'static/images/logos/garbarnia/DRUGony.png'),"
                          " (11, 'Hattrick', 'Hattrick', 'static/images/logos/garbarnia/DRUGony.png');"
                          "insert into team_foreign_ids values (10, 3, 'drug/drug0001'), (11, 3, 'hat/hat00001');")
        con.commit()
        con.close()
        for sid, nazwa in (('drug0001', 'DRUGony'), ('hat00001', 'Hattrick')):
            self.wp.utworz('sportspress/v2/teams', {'title': nazwa, 'slug': nazwa.lower(), 'meta': {'bm_source': 'superscore', 'bm_source_id': sid}})
        _, _, _, r = self._uruchom()
        self.assertEqual(self.a.po_zrodle('teams', 'drug0001')['meta']['bm_logo'], 'garbarnia/DRUGony.png')
        self.assertEqual(self.a.po_zrodle('teams', 'hat00001')['meta']['bm_logo'], 'garbarnia/Hattrick.png')       # nie plik innej drużyny
        self.assertEqual(len(r['powtorzone']), 1)
        self.assertIn('Hattrick', r['powtorzone'][0])

    def test_raport_ma_sekcje(self):
        pary, bez_wp, bez_stare, r = self._uruchom()
        txt = logo.raport('garbarnia', pary, bez_wp, bez_stare, r, ['garbarnia/Inny.png'], False)
        for fragment in ('dopasowane drużyny: 4', 'po NAZWIE PLIKU', 'bez pary w WP', 'UWAGA, stara baza wskazuje plik', 'Inny.png'):
            self.assertIn(fragment, txt)


if __name__ == '__main__':
    unittest.main()
