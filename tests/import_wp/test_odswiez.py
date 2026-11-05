"""W8a: lekki tryb „odśwież wyniki” (tools/import_wp/odswiez.py, uruchamiany plikiem odswiez-wyniki.bat): tylko stan i wynik meczów jednej ligi i sezonu,
nic poza tym; mecz z flagą bm_decyduje (w tym transmitowany) tylko porównywany; blokada przed podwójnym uruchomieniem; komunikat przy braku źródła."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'import_wp'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importuj  # noqa: E402
import odswiez  # noqa: E402
import test_import_nalf as tn  # noqa: E402
import test_import_superscore as ts  # noqa: E402
from atrapa_wp import AtrapaWp  # noqa: E402
from wp_rest import WpRest  # noqa: E402


class OdswiezNalfTests(unittest.TestCase):
    def setUp(self):
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')
        self.imp = importuj.importuj_nalf(self.wp, tn.dane_zrodla(), log=lambda *x: None)
        self.mecz = self.a.po_zrodle('events', tn.ROZEGRANY)
        self.druzyna = str(self.imp.id_wp['druzyny'][7612])
        self.a.wyzeruj_zapytania()

    def _mecze(self, gole=None, usun=()):
        mecze = tn.dane_zrodla()['mecze']
        mecze = [m for m in mecze if m['id'] not in usun]
        if gole is not None:
            next(m for m in mecze if m['id'] == tn.ROZEGRANY)['results']['7612']['goals'] = gole
        return mecze

    def _odswiez(self, mecze, **kw):
        return odswiez.odswiez(self.wp, 'nalf', mecze, 19, 61, **kw)

    def test_bez_zmian_w_zrodle_nic_nie_jest_zapisywane(self):
        w = self._odswiez(self._mecze())
        self.assertEqual((w['zmienione'], w['pominiete'], w['bledy']), ([], [], []))
        self.assertEqual(self.a.posty(), [])
        self.assertEqual(self.a.wyczyszczone, [])

    def test_zmieniony_wynik_zapisuje_tylko_pole_results_bez_czyszczenia_skladu_i_statystyk(self):
        performance_przed = copy.deepcopy(self.mecz['performance'])
        w = self._odswiez(self._mecze(gole='9'))
        self.assertEqual(len(w['zmienione']), 1)
        self.assertIn('było w WP: zakończony 4:', w['zmienione'][0])
        self.assertIn('ze źródła: zakończony 9:', w['zmienione'][0])
        self.assertEqual(self.mecz['results'][self.druzyna]['goals'], '9')
        self.assertEqual(self.mecz['performance'], performance_przed)             # skład i statystyki nietknięte
        self.assertEqual(self.a.wyczyszczone, [])                                 # bez „clear”
        posty = self.a.posty()
        self.assertEqual(len(posty), 1)
        self.assertEqual(sorted(posty[0][2]), ['results'])                        # w żądaniu wyłącznie wynik

    def test_mecz_z_flaga_decyduje_nie_jest_zmieniany_a_roznica_trafia_do_podsumowania(self):
        self.mecz['meta']['bm_decyduje'] = True
        w = self._odswiez(self._mecze(gole='9'))
        self.assertEqual(w['zmienione'], [])
        self.assertEqual(len(w['pominiete']), 1)
        self.assertIn('RÓŻNICA, zostaje wartość z WP', w['pominiete'][0])
        self.assertIn('decyduje użytkownik', w['pominiete'][0])
        self.assertEqual(self.mecz['results'][self.druzyna]['goals'], '4')
        self.assertEqual(self.a.posty(), [])
        tekst = odswiez.podsumowanie('Dywizja A', 'nalf', 3, 2, w, False)
        self.assertIn('Zmieniono meczów: 0', tekst)
        self.assertIn('Pominięte, bo stan i wynik ustala użytkownik (w tym mecz transmitowany): 1', tekst)
        self.assertIn('Źródło odpowiadało: tak', tekst)

    def test_mecz_z_bm_locked_tez_jest_pominiety_a_zgodny_wynik_oznaczony_jako_zgodny(self):
        self.mecz['meta']['bm_locked'] = True
        w = self._odswiez(self._mecze())
        self.assertIn('(zgodne)', w['pominiete'][0])
        self.assertIn('bm_locked', w['pominiete'][0])

    def test_mecz_ze_zrodla_bez_wpisu_w_wp_nie_jest_tworzony_tylko_zgloszony(self):
        self.a.dane['events'].pop(self.mecz['id'])
        w = self._odswiez(self._mecze())
        self.assertEqual(len(w['brak_w_wp']), 1)
        self.assertEqual(self.a.posty(), [])
        self.assertIn('NIE MA W WP', odswiez.podsumowanie('x', 'nalf', 3, 1, w, False))

    def test_na_sucho_pokazuje_zmiane_ale_niczego_nie_zapisuje(self):
        w = self._odswiez(self._mecze(gole='9'), na_sucho=True)
        self.assertEqual(len(w['zmienione']), 1)
        self.assertEqual(self.mecz['results'][self.druzyna]['goals'], '4')
        self.assertEqual(self.a.posty(), [])

    def test_blad_zapisu_jednego_meczu_jest_w_podsumowaniu_a_reszta_idzie_dalej(self):
        self.a.blad_dla = lambda kol, body: kol == 'events'
        w = self._odswiez(self._mecze(gole='9'))
        self.assertEqual(len(w['bledy']), 1)
        self.assertIn('BŁĘDY (1)', odswiez.podsumowanie('x', 'nalf', 3, 1, w, False))


class OdswiezZnikajaceITrybJsonTests(unittest.TestCase):
    def setUp(self):
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')
        importuj.importuj_nalf(self.wp, tn.dane_zrodla(), log=lambda *x: None)
        self.mecz = self.a.po_zrodle('events', tn.ROZEGRANY)

    def _od(self, mecze, **kw):
        return odswiez.odswiez(self.wp, 'nalf', mecze, 19, 61, **kw)

    def test_mecz_ktory_zniknal_ze_zrodla_dostaje_flage_i_nie_jest_usuwany(self):
        reszta = [m for m in tn.dane_zrodla()['mecze'] if m['id'] != tn.PRZYSZLY]
        w = self._od(reszta)
        self.assertEqual(len(w['zniknely']), 1)
        przyszly = self.a.po_zrodle('events', tn.PRZYSZLY)
        self.assertIsNotNone(przyszly)                                       # nic nie usunięto
        self.assertTrue(przyszly['meta']['bm_zrodlo_brak'])
        self.a.wyzeruj_zapytania()
        w = self._od(reszta)                                                 # kolejny raz: flaga już jest, nic nie wysyłamy
        self.assertEqual(w['zniknely'], [])
        self.assertEqual(self.a.posty(), [])

    def test_mecz_ktory_wrocil_do_zrodla_traci_flage(self):
        przyszly = self.a.po_zrodle('events', tn.PRZYSZLY)
        przyszly['meta']['bm_zrodlo_brak'] = True
        w = self._od(tn.dane_zrodla()['mecze'])
        self.assertEqual(len(w['wrocily']), 1)
        self.assertFalse(przyszly['meta']['bm_zrodlo_brak'])

    def test_zrodlo_ktore_oddalo_mniej_niz_polowe_znanych_meczow_nie_flaguje_zniknietych(self):
        w = self._od([m for m in tn.dane_zrodla()['mecze'] if m['id'] == tn.ROZEGRANY])
        self.assertEqual(w['zniknely'], [])
        self.assertTrue(any('awarii źródła' in o for o in w['ostrzezenia']))
        self.assertNotIn('bm_zrodlo_brak', self.a.po_zrodle('events', tn.PRZYSZLY)['meta'])

    def test_mecz_odwolany_w_nalf_wpis_nie_publish_dostaje_flage_a_jego_wynik_nie_jest_ruszany(self):
        mecze = tn.dane_zrodla()['mecze']
        m = next(x for x in mecze if x['id'] == tn.ROZEGRANY)
        m['status'] = 'draft'
        m['results']['7612']['goals'] = '9'
        w = self._od(mecze)
        self.assertEqual(len(w['odwolane']), 1)
        self.assertTrue(self.mecz['meta']['bm_zrodlo_brak'])
        self.assertEqual(self.mecz['results'][str(self.mecz['teams'][0])]['goals'], '4')      # wynik bez zmian

    def test_nalf_bez_wyniku_w_zrodle_nie_czysci_wyniku_w_wp(self):
        mecze = tn.dane_zrodla()['mecze']
        next(x for x in mecze if x['id'] == tn.ROZEGRANY)['results'] = {}
        w = self._od(mecze)
        self.assertEqual(len(w['bez_wyniku_w_zrodle']), 1)
        self.assertIn('results', self.mecz)
        self.assertEqual(self.a.wyczyszczone_wyniki, [])

    def test_flaga_brak_jest_ustawiana_takze_dla_meczu_z_flaga_decyduje(self):
        self.mecz['meta']['bm_decyduje'] = True
        mecze = [m for m in tn.dane_zrodla()['mecze'] if m['id'] != tn.ROZEGRANY]
        w = self._od(mecze)
        self.assertEqual(len(w['zniknely']), 1)                              # flaga to nie stan ani wynik
        self.assertTrue(self.mecz['meta']['bm_zrodlo_brak'])

    def test_tryb_json_zwraca_jedna_linie_z_wynikiem_a_blad_zrodla_tez_jako_json(self):
        import io
        from contextlib import redirect_stdout
        tmp = Path(tempfile.mkdtemp(prefix='bm-odswiez-json-'))
        with mock.patch.object(odswiez.importuj, 'wp_dir', return_value=tmp),                 mock.patch.object(odswiez.importuj, 'polacz_z_wp', return_value=(self.wp, 8091, 'nalf')),                 mock.patch.object(odswiez, 'pobierz_ze_zrodla', return_value=(tn.dane_zrodla()['mecze'], 2)):
            bufor = io.StringIO()
            with redirect_stdout(bufor):
                kod = odswiez.main(['nalf', '--liga', '19', '--sezon', '61', '--json'])
        dane = json.loads(bufor.getvalue())
        self.assertEqual((kod, dane['ok'], dane['zrodlo_odpowiadalo'], dane['meczow_w_zrodle']), (0, True, True, 3))
        self.assertIn('wynik', dane)
        with mock.patch.object(odswiez.importuj, 'wp_dir', return_value=tmp),                 mock.patch.object(odswiez.importuj, 'polacz_z_wp', return_value=(self.wp, 8091, 'nalf')),                 mock.patch.object(odswiez, 'pobierz_ze_zrodla', side_effect=OSError('brak sieci')):
            bufor = io.StringIO()
            with redirect_stdout(bufor):
                kod = odswiez.main(['nalf', '--liga', '19', '--sezon', '61', '--json'])
        dane = json.loads(bufor.getvalue())
        self.assertEqual((kod, dane['ok']), (2, False))
        self.assertIn('ŹRÓDŁO NIE ODPOWIADA', dane['blad'])


class OdswiezSuperscoreTests(unittest.TestCase):
    def setUp(self):
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')
        importuj.importuj_zrodlo(self.wp, 'superscore', ts.dane(), log=lambda *x: None)
        self.a.wyzeruj_zapytania()
        self.liga, self.sezon = '0loc9tw7', '33lvZK65l7ubf6BfFPjtl'

    def _mecze(self, api=None):
        return [m for m in ts.dane(api)['mecze']]

    def test_zmiana_wyniku_na_zywo_idzie_trasa_source_state_bez_dotykania_tresci_meczu(self):
        fx = copy.deepcopy(ts.FX['fixtures'])
        e = next(x for x in fx['events'] if x['id'] == ts.W_TOKU)
        next(s for s in e['scores'] if s['type'] == 0)['team1'] = 4
        w = odswiez.odswiez(self.wp, 'superscore', self._mecze(ts.AtrapaSuperscore(fx)), self.liga, self.sezon)
        self.assertEqual(self.a.po_zrodle('events', ts.W_TOKU)['meta']['bm_live_score'], '4:0')
        self.assertEqual(self.a.stany, [(self.a.po_zrodle('events', ts.W_TOKU)['id'], 'trwa', '4:0')])
        self.assertEqual((self.a.posty(), self.a.wyczyszczone), ([], []))
        self.assertEqual(len(w['zmienione']), 1)

    def test_mecz_transmitowany_z_flaga_jest_pominiety_i_zgloszony_w_podsumowaniu(self):
        mecz = self.a.po_zrodle('events', ts.W_TOKU)
        mecz['meta'].update({'bm_decyduje': True, 'bm_live_score': '0:0'})
        w = odswiez.odswiez(self.wp, 'superscore', self._mecze(), self.liga, self.sezon)
        self.assertEqual(self.a.stany, [])
        self.assertEqual(mecz['meta']['bm_live_score'], '0:0')
        self.assertIn('źródło: trwa 1:0, WP: trwa 0:0 (RÓŻNICA', w['pominiete'][0])

    def test_zrodlo_mowi_nierozpoczety_a_wp_ma_wynik_czyszczenie_przez_source_state_z_poprzednia_wartoscia(self):
        zak = self.a.po_zrodle('events', ts.ZAKONCZONY)
        self.assertIn('results', zak)
        fx = copy.deepcopy(ts.FX['fixtures'])
        e = next(x for x in fx['events'] if x['id'] == ts.ZAKONCZONY)
        e['match_state'], e['scores'], e['match_status'] = 0, [], 0
        w = odswiez.odswiez(self.wp, 'superscore', self._mecze(ts.AtrapaSuperscore(fx)), self.liga, self.sezon)
        self.assertNotIn('results', zak)                                     # natywny wynik wyczyszczony
        self.assertEqual(zak['meta']['bm_state'], 'nierozpoczety')
        self.assertTrue(any('było w WP: zakończony' in z and 'ze źródła: nierozpoczęty' in z for z in w['zmienione']))

    def test_mecz_nierozpoczety_w_zrodle_i_w_wp_nie_generuje_zapisu(self):
        self.a.wyzeruj_zapytania()
        odswiez.odswiez(self.wp, 'superscore', self._mecze(), self.liga, self.sezon)
        self.assertEqual([s for s in self.a.stany if s[0] == self.a.po_zrodle('events', ts.NIEROZPOCZETY)['id']], [])

    def test_mecz_superscore_w_nietypowym_statusie_jest_flagowany_a_jego_stan_nie_zmieniany(self):
        fx = copy.deepcopy(ts.FX['fixtures'])
        e = next(x for x in fx['events'] if x['id'] == ts.NIEROZPOCZETY)
        e['match_status'] = 5                                                # np. przełożony
        w = odswiez.odswiez(self.wp, 'superscore', self._mecze(ts.AtrapaSuperscore(fx)), self.liga, self.sezon)
        mecz = self.a.po_zrodle('events', ts.NIEROZPOCZETY)
        self.assertTrue(mecz['meta']['bm_zrodlo_brak'])
        self.assertEqual(len(w['odwolane']), 1)
        self.assertIn('status 5', w['odwolane'][0])

    def test_wybor_rozgrywek_niezgodny_ze_zrodla_json_jest_odrzucony(self):
        with self.assertRaises(SystemExit) as cm:
            odswiez.pobierz_ze_zrodla('garbarnia', 'inna', self.sezon)
        self.assertIn('Wybierz właściwe rozgrywki', str(cm.exception))


class BlokadaITrybTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='bm-odswiez-'))

    def test_druga_blokada_jest_odrzucona_a_po_zwolnieniu_mozna_zalozyc_nowa(self):
        sciezka = self.tmp / 'odswiez-wyniki.lock'
        with odswiez.Blokada(sciezka):
            with self.assertRaises(odswiez.Zajete) as cm:
                with odswiez.Blokada(sciezka):
                    pass
            self.assertIn('już trwa', str(cm.exception))
            self.assertTrue(sciezka.exists())               # nieudana próba nie zwalnia cudzej blokady
        self.assertFalse(sciezka.exists())
        with odswiez.Blokada(sciezka):
            pass

    def test_przestarzala_blokada_po_przerwanym_uruchomieniu_jest_zastapiona(self):
        sciezka = self.tmp / 'odswiez-wyniki.lock'
        sciezka.write_text('1')
        stary = sciezka.stat().st_mtime - odswiez.BLOKADA_WAZNA_S - 5
        os.utime(sciezka, (stary, stary))
        with odswiez.Blokada(sciezka):
            self.assertTrue(sciezka.exists())

    def test_wybor_rozgrywek_z_pliku_modulu_i_brak_wyboru(self):
        with mock.patch.object(odswiez, 'REPO', self.tmp):
            inst = self.tmp / 'modules' / 'futsal_nalf' / 'instance'
            inst.mkdir(parents=True)
            self.assertIsNone(odswiez.wybor_rozgrywek('futsal_nalf'))
            (inst / 'wp_rozgrywki.json').write_text(json.dumps({'default': {'league_slug': 'nalf-l19', 'season_slug': 'nalf-s61', 'league_name': 'Dywizja A',
                                                                             'season_name': 'Jesień 2026'}}), encoding='utf-8')
            self.assertEqual(odswiez.wybor_rozgrywek('futsal_nalf'), {'liga': '19', 'sezon': '61', 'nazwa': 'Dywizja A — Jesień 2026'})
            (inst / 'wp_rozgrywki.json').write_text(json.dumps({'default': None}), encoding='utf-8')
            self.assertIsNone(odswiez.wybor_rozgrywek('futsal_nalf'))

    def test_nalf_pobiera_tylko_wyniki_wybranej_ligi_bez_skladow(self):
        zapytania = []

        class Api:
            zapytania = 1

            def get_all(self, zasob, **params):
                zapytania.append((zasob, params))
                return copy.deepcopy(tn.FX['events'])
        with mock.patch.object(odswiez.zrodlo_nalf, 'NalfApi', lambda cache_dir=None: Api()):
            mecze, n = odswiez.pobierz_ze_zrodla('nalf', '19', '61')
        self.assertEqual(len(mecze), 3)
        self.assertEqual(len(zapytania), 1)
        self.assertEqual((zapytania[0][0], zapytania[0][1]['leagues'], zapytania[0][1]['seasons']), ('events', 19, 61))
        self.assertNotIn('performance', zapytania[0][1]['_fields'])
        self.assertNotIn('players', zapytania[0][1]['_fields'].split(','))

    def test_zrodlo_nie_odpowiada_to_czytelny_komunikat_bez_zmian_w_wp(self):
        wybor = {'liga': '19', 'sezon': '61', 'nazwa': 'Dywizja A'}
        with mock.patch.object(odswiez, 'wybor_rozgrywek', return_value=wybor), \
                mock.patch.object(odswiez.importuj, 'wp_dir', return_value=self.tmp), \
                mock.patch.object(odswiez.importuj, 'polacz_z_wp', return_value=(mock.MagicMock(), 8091, 'nalf')), \
                mock.patch.object(odswiez, 'pobierz_ze_zrodla', side_effect=OSError('brak sieci')):
            with self.assertRaises(SystemExit) as cm:
                odswiez.main(['nalf'])
        self.assertIn('ŹRÓDŁO NIE ODPOWIADA', str(cm.exception))
        self.assertIn('Nic nie zmieniono', str(cm.exception))
        self.assertFalse((self.tmp / 'odswiez-wyniki.lock').exists())          # blokada zwolniona mimo błędu


if __name__ == '__main__':
    unittest.main()
