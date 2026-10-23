"""Etap I1: importer NALF (tools/import_wp): normalizacja odpowiedzi API, klient API, zapis do WP (atrapa), powtarzalność.

    python -m unittest discover tests/import_wp          (z katalogu głównego repozytorium)

Dane: tests/import_wp/dane/nalf_sezon.json to wycinek PRAWDZIWYCH odpowiedzi API nalffutsal.pl (sezon Jesień 2026): mecz rozegrany ze składem,
mecz przyszły (results to pusta lista) i mecz fazy pucharowej z wolnymi miejscami (drużyny 0, 0)."""
import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'import_wp'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importuj  # noqa: E402
import nalf  # noqa: E402
from atrapa_wp import AtrapaWp  # noqa: E402
from wp_rest import WpRest  # noqa: E402

FX = json.loads((Path(__file__).resolve().parent / 'dane' / 'nalf_sezon.json').read_text(encoding='utf-8'))
ROZEGRANY, PRZYSZLY, PUCHAROWY = 10834, 10894, 10856


class AtrapaZrodla:
    """Udaje odpowiedzi API nalffutsal.pl z fixtury (wszystko na jednej stronie)."""

    def __init__(self, fx):
        self.fx = fx
        self.zapytania = 0
        self.z_pamieci = 0

    def get_all(self, zasob, **params):
        self.zapytania += 1
        return copy.deepcopy(self.fx[zasob])


def dane_zrodla(fx=None):
    return nalf.pobierz_sezon(AtrapaZrodla(fx or FX), 61, log=lambda *a: None)


class NormalizacjaTests(unittest.TestCase):
    def test_mecz_rozegrany_ma_wyniki_sklad_i_statystyki_bez_pozycji(self):
        m = next(x for x in dane_zrodla()['mecze'] if x['id'] == ROZEGRANY)
        self.assertEqual(set(m['results']), {'7612', '10308'})
        self.assertEqual(m['results']['7612']['goals'], '4')
        self.assertEqual(m['results']['7612']['outcome'], ['win'])
        self.assertEqual(m['teams'], [7612, 10308])
        for rows in m['performance'].values():
            for w in rows.values():
                self.assertNotIn('position', w)
                self.assertLessEqual(set(w), set(nalf.STATYSTYKI))
        self.assertIn('6811', m['performance']['7612'])

    def test_mecz_przyszly_nie_ma_wynikow_a_pucharowy_ma_wolne_miejsca(self):
        mecze = {x['id']: x for x in dane_zrodla()['mecze']}
        self.assertEqual(mecze[PRZYSZLY]['results'], {})
        self.assertEqual(mecze[PRZYSZLY]['performance'], {})
        self.assertEqual(mecze[PUCHAROWY]['teams'], [0, 0])

    def test_zawodnik_bez_numeru_ma_none_a_druzyna_skrot_i_slug(self):
        d = dane_zrodla()
        self.assertTrue(all(p['number'] is None or isinstance(p['number'], int) for p in d['zawodnicy']))
        t = next(t for t in d['druzyny'] if t['id'] == 10308)
        self.assertEqual((t['name'], t['slug']), ('K2', 'k2-2'))
        self.assertEqual(set(d['ligi']), {19, 20, 31})

    def test_nieznany_sezon_to_czytelny_blad(self):
        with self.assertRaises(SystemExit) as cm:
            nalf.pobierz_sezon(AtrapaZrodla(FX), 999, log=lambda *a: None)
        self.assertIn('Źródło nie ma sezonu o id 999', str(cm.exception))


class KlientApiTests(unittest.TestCase):
    class Odp:
        def __init__(self, body, strony=1):
            self.body, self.headers = body, {'X-WP-TotalPages': str(strony)}

        def read(self):
            return json.dumps(self.body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def test_pamiec_podreczna_i_stronicowanie(self):
        wywolania = []

        def opener(req, timeout=0):
            wywolania.append(req.full_url)
            strona = int(re.search(r'[?&]page=(\d+)', req.full_url).group(1))
            return self.Odp([{'id': strona}], strony=2)

        with tempfile.TemporaryDirectory() as d:
            api = nalf.NalfApi(cache_dir=d, przerwa=0, opener=opener)
            self.assertEqual(api.get_all('teams', seasons=61), [{'id': 1}, {'id': 2}])
            self.assertEqual(len(wywolania), 2)
            api2 = nalf.NalfApi(cache_dir=d, przerwa=0, opener=opener)
            self.assertEqual(api2.get_all('teams', seasons=61), [{'id': 1}, {'id': 2}])
            self.assertEqual((len(wywolania), api2.z_pamieci), (2, 2))               # drugi raz z pamięci

    def test_bez_katalogu_pamieci_kazde_wywolanie_idzie_do_strony(self):
        n = []
        api = nalf.NalfApi(przerwa=0, opener=lambda req, timeout=0: (n.append(1), self.Odp([]))[1])
        api.get_all('teams')
        api.get_all('teams')
        self.assertEqual(len(n), 2)


class ImportDoWpTests(unittest.TestCase):
    def setUp(self):
        self.wp_atrapa = AtrapaWp()
        self.addCleanup(self.wp_atrapa.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.wp_atrapa.port}', 'operator', 'tajne')

    def _importuj(self, dane=None, **kw):
        return importuj.importuj_nalf(self.wp, dane or dane_zrodla(), log=lambda *a: None, **kw)

    def test_pierwszy_import_tworzy_kategorie_druzyny_zawodnikow_i_mecze_z_mapowaniem_id(self):
        imp = self._importuj()
        a = self.wp_atrapa
        self.assertEqual((len(a.dane['seasons']), len(a.dane['leagues']), len(a.dane['teams']), len(a.dane['players']), len(a.dane['events'])),
                         (1, 3, 3, 6, 3))
        self.assertEqual(sorted(o['slug'] for o in a.dane['leagues'].values()), ['nalf-l19', 'nalf-l20', 'nalf-l31'])
        self.assertEqual(next(iter(a.dane['seasons'].values()))['slug'], 'nalf-s61')
        druzyna = a.po_zrodle('teams', 7612)
        self.assertEqual(druzyna['slug'], 'galactik-futsal')
        self.assertEqual(druzyna['meta']['bm_source'], 'nalf')
        mecz = a.po_zrodle('events', ROZEGRANY)
        self.assertEqual(mecz['teams'], [imp.id_wp['druzyny'][7612], imp.id_wp['druzyny'][10308]])
        self.assertEqual(mecz['results'][str(imp.id_wp['druzyny'][7612])]['goals'], '4')
        gracz = imp.id_wp['zawodnicy'][6811]
        self.assertIn(str(gracz), mecz['performance'][str(imp.id_wp['druzyny'][7612])])
        self.assertIn(gracz, mecz['players'])
        self.assertEqual(mecz['seasons'], [imp.id_wp['sezon'][61]])
        self.assertEqual(mecz['title'], 'Galactik Futsal - K2')

    def test_mecz_przyszly_bez_wynikow_a_pucharowy_z_wolnymi_miejscami(self):
        self._importuj()
        przyszly = self.wp_atrapa.po_zrodle('events', PRZYSZLY)
        self.assertNotIn('results', przyszly)
        self.assertNotIn('performance', przyszly)
        pucharowy = self.wp_atrapa.po_zrodle('events', PUCHAROWY)
        self.assertEqual(pucharowy['teams'], [0, 0])
        self.assertEqual(pucharowy['title'], 'Do ustalenia - Do ustalenia')

    def test_drugi_import_niczego_nie_dubluje_i_niczego_nie_wysyla(self):
        self._importuj()
        liczba = {k: len(v) for k, v in self.wp_atrapa.dane.items()}
        self.wp_atrapa.wyzeruj_zapytania()
        imp = self._importuj()
        self.assertEqual({k: len(v) for k, v in self.wp_atrapa.dane.items()}, liczba)
        self.assertEqual(self.wp_atrapa.posty(), [])
        for rodzaj in ('druzyny', 'zawodnicy', 'mecze'):
            l = imp.liczniki[rodzaj]
            self.assertEqual((l.nowe, l.zmienione, l.bledy), (0, 0, 0), rodzaj)
        self.assertEqual(imp.liczniki['mecze'].bez_zmian, 3)

    def test_zmiana_wyniku_i_skladu_w_zrodle_czysci_stare_dane_i_zapisuje_tylko_ten_mecz(self):
        self._importuj()
        d = dane_zrodla()
        m = next(x for x in d['mecze'] if x['id'] == ROZEGRANY)
        m['results']['7612']['goals'] = '9'
        del m['performance']['7612']['6811']
        m['players'] = [p for p in m['players'] if p != 6811]
        self.wp_atrapa.wyzeruj_zapytania()
        imp = self._importuj(d)
        self.assertEqual((imp.liczniki['mecze'].zmienione, imp.liczniki['mecze'].bez_zmian), (1, 2))
        self.assertEqual(len(self.wp_atrapa.posty()), 1)
        mecz = self.wp_atrapa.po_zrodle('events', ROZEGRANY)
        self.assertEqual(self.wp_atrapa.wyczyszczone, [mecz['id']])               # stare wyniki i skład wyczyszczone przed zapisem
        wp_druzyna = str(imp.id_wp['druzyny'][7612])
        self.assertEqual(mecz['results'][wp_druzyna]['goals'], '9')
        self.assertNotIn(str(imp.id_wp['zawodnicy'][6811]), mecz['performance'][wp_druzyna])

    def test_mecz_z_blokada_wyniku_albo_trwajacy_jest_pomijany(self):
        self._importuj()
        mecz = self.wp_atrapa.po_zrodle('events', ROZEGRANY)
        mecz['meta']['bm_locked'] = True
        d = dane_zrodla()
        next(x for x in d['mecze'] if x['id'] == ROZEGRANY)['results']['7612']['goals'] = '9'
        self.wp_atrapa.wyzeruj_zapytania()
        imp = self._importuj(d)
        l = imp.liczniki['mecze']
        self.assertEqual((l.pominiete, l.zmienione), (1, 0))
        self.assertEqual(self.wp_atrapa.posty(), [])
        self.assertEqual(mecz['results'][str(imp.id_wp['druzyny'][7612])]['goals'], '4')

    def test_na_sucho_nic_nie_zapisuje_ale_liczy_zmiany(self):
        imp = self._importuj(na_sucho=True)
        self.assertEqual(self.wp_atrapa.posty(), [])
        self.assertEqual({k: len(v) for k, v in self.wp_atrapa.dane.items()}, {k: 0 for k in self.wp_atrapa.dane})
        self.assertEqual((imp.liczniki['druzyny'].nowe, imp.liczniki['zawodnicy'].nowe, imp.liczniki['mecze'].nowe), (3, 6, 3))

    def test_blad_jednego_rekordu_nie_przerywa_importu_a_powtorka_dopisuje_brakujacy(self):
        self.wp_atrapa.blad_dla = lambda kol, body: kol == 'players' and body['meta']['bm_source_id'] == '7775'
        imp = self._importuj()
        self.assertEqual(imp.liczniki['zawodnicy'].bledy, 1)
        self.assertEqual(len(self.wp_atrapa.dane['players']), 5)
        self.assertEqual(len(self.wp_atrapa.dane['events']), 3)                  # mecze zapisane mimo błędu zawodnika
        self.wp_atrapa.blad_dla = None
        imp = self._importuj()
        self.assertEqual((imp.liczniki['zawodnicy'].nowe, imp.liczniki['zawodnicy'].bez_zmian), (1, 5))
        self.assertEqual(len(self.wp_atrapa.dane['players']), 6)

    def test_bez_zawodnikow_importuje_druzyny_i_mecze_bez_skladow(self):
        imp = self._importuj(z_zawodnikami=False)
        self.assertEqual(len(self.wp_atrapa.dane['players']), 0)
        self.assertNotIn('performance', self.wp_atrapa.po_zrodle('events', ROZEGRANY))
        self.assertEqual(imp.liczniki['mecze'].nowe, 3)

    def test_rekordy_z_wp_ktorych_nie_ma_w_zrodle_trafiaja_do_raportu_bez_usuwania(self):
        self._importuj()
        d = dane_zrodla()
        d['mecze'] = [m for m in d['mecze'] if m['id'] != PRZYSZLY]
        imp = self._importuj(d)
        self.assertEqual(imp.liczniki['mecze'].nie_ma_w_zrodle, [str(PRZYSZLY)])
        self.assertEqual(len(self.wp_atrapa.dane['events']), 3)
        self.assertIn('nic nie usuwam', importuj.raport(imp, False))

    def test_rekord_innego_zrodla_nie_jest_dopasowywany(self):
        self._importuj()
        for o in self.wp_atrapa.dane['teams'].values():
            o['meta']['bm_source'] = 'superscore'
        self.wp_atrapa.wyzeruj_zapytania()
        imp = self._importuj()
        self.assertEqual(imp.liczniki['druzyny'].nowe, 3)
        self.assertEqual(len(self.wp_atrapa.dane['teams']), 6)


if __name__ == '__main__':
    unittest.main()
