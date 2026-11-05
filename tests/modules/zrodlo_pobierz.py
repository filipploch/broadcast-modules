"""W8a2: „Pobierz” ze źródła zewnętrznego (core/managers/zrodlo.py, trasy /api/zrodlo/*): deklaracja źródła w module.json, ukrywanie bez źródła, rozwiązanie pary
liga/sezon, praca w tle z blokadą, limit czasu podprocesu, podsumowanie. Wspólne dla obu modułów: make(APP, 'futsal_nalf'|'garbarnia'). Źródło i WP to atrapy
(prawdziwy import sprawdzają testy importerów w tests/import_wp, prawdziwy WP: dry_run_w8a_wp.py)."""
import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import harness

WYNIK_ZRODLA = {'ok': True, 'blad': '', 'tekst': 'ODŚWIEŻENIE WYNIKÓW: Dywizja A\nZmieniono meczów: 1:\n  - A - B: było w WP: trwa 0:0, ze źródła: zakończony 2:1',
                 'wynik': {'zmienione': ['A - B: ...'], 'pominiete': []}, 'zrodlo_odpowiadalo': True, 'meczow_w_zrodle': 3}
WYNIK_MODULU = {'ok': True, 'zapisano': True, 'kopia_kb': 1004, 'kopia_ms': 41,
                'raport': {'liczniki': {'mecze': {'dodano': 0, 'zaktualizowano': 1, 'bez_zmian': 2, 'pominieto': 0}}, 'pominiete': ['C - D: NA ANTENIE: mecz aktywny w sesji'],
                           'zmiany': ['mecz A - B: wynik 2:1'], 'bledy': [], 'kopia': 'x/kopie-wp/database-1.db'}}


def make(APP, modul):
    class ZrodloPobierz(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.managers.zrodlo import Zrodlo
            self.cm, self.Zrodlo = cm, Zrodlo
            cm._zrodlo = None
            self.wp = cm.get_wp_manager()
            self._stare = (self.wp._list, self.wp._default, self.wp.pull)
            self.wp._list = {'items': [
                {'key': '820:819', 'league_id': 820, 'season_id': 819, 'league_name': 'Dywizja A', 'season_name': 'Jesień 2026',
                 'league_slug': 'nalf-l19' if modul == 'futsal_nalf' else 'superscore-l0loc9tw7',
                 'season_slug': 'nalf-s61' if modul == 'futsal_nalf' else 'superscore-s33lvzk65l7ubf6bffpjtl'},
                {'key': '5:6', 'league_id': 5, 'season_id': 6, 'league_name': 'Obca', 'season_name': 'X', 'league_slug': 'inne-l1', 'season_slug': 'inne-s1'}]}
            self.wp._default = {'key': '820:819'}
            self.wywolania_pull = []
            self.wp.pull = lambda *a: self.wywolania_pull.append(a) or dict(WYNIK_MODULU)
            self.uruchomienia = []
            self.odp_zrodla = dict(WYNIK_ZRODLA)
            self.bramka = None
            APP.config['ZRODLO_URUCHOM'] = self._uruchom
            self.client = APP.test_client()

        def tearDown(self):
            self.wp._list, self.wp._default, self.wp.pull = self._stare
            APP.config.pop('ZRODLO_URUCHOM', None)
            APP.config.pop('ZRODLO_TYP', None)
            self.cm._zrodlo = None
            self.ctx.pop()

        def _uruchom(self, para):
            self.uruchomienia.append(dict(para))
            if self.bramka is not None:
                self.bramka.wait(10)
            return dict(self.odp_zrodla)

        def czekaj_na_koniec(self, limit=10):
            t0 = time.time()
            while time.time() - t0 < limit:
                s = self.client.get('/api/zrodlo/status').get_json()
                if not s['w_toku']:
                    return s
                time.sleep(0.05)
            self.fail('praca nie skończyła się')

        # ---- deklaracja źródła i ukrywanie
        def test_deklaracja_zrodla_w_source_json_obu_modulow(self):
            from core.managers.zrodlo import wczytaj_blok_zrodla
            katalog = Path(APP.config.get('MODULE_DIR'))
            typ, mid = wczytaj_blok_zrodla(katalog)
            self.assertEqual((typ, mid), (('nalffutsal', 'nalf') if modul == 'futsal_nalf' else ('superscore', 'garbarnia')))
            tmp = Path(tempfile.mkdtemp(prefix='bm-zrodlo-'))
            self.assertEqual(wczytaj_blok_zrodla(tmp), ('brak', ''))                       # brak pliku
            (tmp / 'module.json').write_text(json.dumps({'id': 'x'}), encoding='utf-8')
            self.assertEqual(wczytaj_blok_zrodla(tmp), ('brak', 'x'))                      # brak pliku source.json
            (tmp / 'source.json').write_text(json.dumps({'typ': 'cos'}), encoding='utf-8')
            self.assertEqual(wczytaj_blok_zrodla(tmp), ('brak', 'x'))                      # nieznany typ
            (tmp / 'source.json').write_text('to nie json', encoding='utf-8')
            self.assertEqual(wczytaj_blok_zrodla(tmp), ('brak', 'x'))                      # uszkodzony plik
            (tmp / 'source.json').write_text(json.dumps({'typ': 'superscore'}), encoding='utf-8')
            self.assertEqual(wczytaj_blok_zrodla(tmp), ('superscore', 'x'))

        def test_module_json_nie_ma_pola_source_bo_hub_czyta_go_scisle(self):
            katalog = Path(APP.config.get('MODULE_DIR'))
            self.assertNotIn('source', json.loads((katalog / 'module.json').read_text(encoding='utf-8-sig')))

        def test_status_ze_zrodlem_i_bez(self):
            s = self.client.get('/api/zrodlo/status').get_json()
            self.assertTrue(s['dostepne'])
            self.assertFalse(s['w_toku'])
            APP.config['ZRODLO_TYP'] = 'brak'
            self.cm._zrodlo = None
            s = self.client.get('/api/zrodlo/status').get_json()
            self.assertFalse(s['dostepne'])
            self.assertIn('nie ma źródła', s['powod'])

        def test_bez_zrodla_pobieranie_jest_odrzucone_i_nic_sie_nie_uruchamia(self):
            APP.config['ZRODLO_TYP'] = 'brak'
            self.cm._zrodlo = None
            odp = self.client.post('/api/zrodlo/pobierz', json={})
            self.assertEqual(odp.status_code, 409)
            self.assertEqual((self.uruchomienia, self.wywolania_pull), ([], []))

        # ---- para liga/sezon
        def test_para_z_wyboru_domyslnego_gdy_nie_podano_ligi(self):
            odp = self.client.post('/api/zrodlo/pobierz', json={})
            self.assertEqual(odp.status_code, 202)
            self.czekaj_na_koniec()
            self.assertEqual(self.uruchomienia[0]['liga_wp'], 820)
            self.assertEqual(self.uruchomienia[0]['liga'], '19' if modul == 'futsal_nalf' else '0loc9tw7')
            self.assertEqual(self.wywolania_pull[0][-2:], (820, 819))

        def test_para_z_powiazania_ligi_modulu_z_wp(self):
            from core.models.base_league_foreign_id import get_league_foreign_id_model
            from core.models.base_scraper import get_scraper_model
            from core.extensions import db
            sc = get_scraper_model()(name='wp', folder='wp')
            db.session.add(sc)
            db.session.commit()
            db.session.add(get_league_foreign_id_model()(scraper_id=sc.id, league_id=self.ids['league'], foreign_id='820:819'))
            db.session.commit()
            odp = self.client.post('/api/zrodlo/pobierz', json={'league_id': self.ids['league']})
            self.assertEqual(odp.status_code, 202)
            self.czekaj_na_koniec()
            self.assertEqual(self.uruchomienia[0]['sezon_wp'], 819)

        def test_liga_modulu_nie_pobrana_z_wp_dostaje_komunikat_bez_uruchomienia(self):
            odp = self.client.post('/api/zrodlo/pobierz', json={'league_id': self.ids['league']})
            self.assertEqual(odp.status_code, 409)
            self.assertIn('nie pochodzi z WP', odp.get_json()['error'])
            self.assertEqual(self.uruchomienia, [])

        def test_rozgrywki_z_innego_zrodla_sa_odrzucone(self):
            self.wp._default = {'key': '5:6'}
            odp = self.client.post('/api/zrodlo/pobierz', json={})
            self.assertEqual(odp.status_code, 409)
            self.assertIn('nie pochodzą ze źródła', odp.get_json()['error'])

        def test_brak_wybranych_rozgrywek_daje_komunikat(self):
            self.wp._default = None
            odp = self.client.post('/api/zrodlo/pobierz', json={})
            self.assertEqual(odp.status_code, 409)
            self.assertIn('wybierz rozgrywki', odp.get_json()['error'])

        # ---- praca w tle, blokada, podsumowanie
        def test_przebieg_zrodlo_potem_modul_a_podsumowanie_ma_obie_czesci(self):
            odp = self.client.post('/api/zrodlo/pobierz', json={})
            self.assertEqual(odp.status_code, 202)
            s = self.czekaj_na_koniec()
            w = s['wynik']
            self.assertTrue(w['ok'])
            self.assertIn('1. ŹRÓDŁO -> WP', w['tekst'])
            self.assertIn('Zmieniono meczów: 1', w['tekst'])
            self.assertIn('2. WP -> MODUŁ', w['tekst'])
            self.assertIn('zaktualizowano 1', w['tekst'])
            self.assertIn('pominięty: C - D: NA ANTENIE', w['tekst'])                       # mecz transmitowany w raporcie modułu
            self.assertIn('1004 KB, 41 ms', w['tekst'])                                    # rozmiar i czas kopii bazy
            self.assertEqual(len(self.uruchomienia), 1)
            self.assertEqual(self.wywolania_pull[0][0], True)                              # apply=True: dane trafiają do modułu automatycznie

        def test_drugi_klik_w_trakcie_pracy_jest_odrzucony(self):
            self.bramka = threading.Event()
            self.assertEqual(self.client.post('/api/zrodlo/pobierz', json={}).status_code, 202)
            s = self.client.get('/api/zrodlo/status').get_json()
            self.assertTrue(s['w_toku'])
            self.assertEqual(s['etap'], 'źródło')
            odp = self.client.post('/api/zrodlo/pobierz', json={})
            self.assertEqual(odp.status_code, 409)
            self.assertIn('już trwa', odp.get_json()['error'])
            self.bramka.set()
            self.czekaj_na_koniec()
            self.assertEqual(len(self.uruchomienia), 1)

        def test_blad_zrodla_nie_blokuje_pobrania_z_wp_a_wynik_jest_nieudany_z_komunikatem(self):
            self.odp_zrodla = {'ok': False, 'blad': 'ŹRÓDŁO NIE ODPOWIADA (brak sieci). Nic nie zmieniono w WP.'}
            self.client.post('/api/zrodlo/pobierz', json={})
            w = self.czekaj_na_koniec()['wynik']
            self.assertFalse(w['ok'])
            self.assertIn('ŹRÓDŁO NIE ODPOWIADA', w['tekst'])
            self.assertEqual(len(self.wywolania_pull), 1)                                  # WP -> moduł nadal się wykonuje

        def test_import_zablokowany_przez_drugie_uruchomienie_nie_wola_pobierania_z_wp(self):
            self.odp_zrodla = {'ok': False, 'blad': 'Odświeżanie już trwa (zaczęte 3 s temu). Poczekaj na jego koniec.'}
            self.client.post('/api/zrodlo/pobierz', json={})
            w = self.czekaj_na_koniec()['wynik']
            self.assertFalse(w['ok'])
            self.assertEqual(self.wywolania_pull, [])

        def test_wyjatek_w_imporcie_albo_pobieraniu_konczy_prace_bez_zawieszenia(self):
            def zly(_):
                raise RuntimeError('boom')
            APP.config['ZRODLO_URUCHOM'] = zly
            self.cm._zrodlo = None
            self.wp.pull = lambda *a: (_ for _ in ()).throw(ValueError('baza'))
            self.client.post('/api/zrodlo/pobierz', json={})
            s = self.czekaj_na_koniec()
            self.assertFalse(s['w_toku'])
            self.assertIn('Błąd importu: boom', s['wynik']['tekst'])
            self.assertIn('Błąd pobierania z WP: baza', s['wynik']['tekst'])

        # ---- podproces: limit czasu i odczyt wyniku
        def _zrodlo(self):
            from core.managers.zrodlo import Zrodlo
            z = Zrodlo(APP.config.get('MODULE_DIR'))
            return z, {'liga': '19', 'sezon': '61', 'liga_wp': 820, 'sezon_wp': 819, 'nazwa': 'x'}

        def test_podproces_limit_120_s_i_komunikat(self):
            z, para = self._zrodlo()
            with mock.patch('core.managers.zrodlo.subprocess.run', side_effect=subprocess.TimeoutExpired('x', 120)) as run:
                w = z._uruchom_podproces(para)
            self.assertFalse(w['ok'])
            self.assertIn('120', w['blad'])
            self.assertEqual(run.call_args.kwargs['timeout'], 120)
            polecenie = run.call_args.args[0]
            self.assertIn('--json', polecenie)
            self.assertEqual(polecenie[polecenie.index('--liga') + 1], '19')

        def test_podproces_czyta_ostatnia_linie_json_a_brak_wyniku_to_blad(self):
            z, para = self._zrodlo()
            ok = mock.Mock(stdout='szum\n{"ok": true, "tekst": "t"}\n', stderr='', returncode=0)
            with mock.patch('core.managers.zrodlo.subprocess.run', return_value=ok):
                self.assertEqual(z._uruchom_podproces(para), {'ok': True, 'tekst': 't'})
            zly = mock.Mock(stdout='', stderr='Traceback...', returncode=1)
            with mock.patch('core.managers.zrodlo.subprocess.run', return_value=zly):
                w = z._uruchom_podproces(para)
            self.assertFalse(w['ok'])
            self.assertIn('Traceback', w['blad'])

    return ZrodloPobierz


def make_node():
    """Przycisk „Pobierz” (prawdziwy kod zrodlo-pobierz.js w Node): wchodzi do zestawu modułu."""
    import shutil

    class ZrodloPobierzNode(unittest.TestCase):
        def test_zrodlo_pobierz_w_node(self):
            node = shutil.which('node')
            if node is None:
                raise RuntimeError('Brak Node.js w PATH')
            skrypt = Path(__file__).resolve().parent / 'js' / 'zrodlo_pobierz_test.js'
            r = subprocess.run([node, str(skrypt)], capture_output=True, text=True, encoding='utf-8', timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('OK 5 przypadków', r.stdout)

    return ZrodloPobierzNode
