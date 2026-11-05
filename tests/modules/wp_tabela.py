"""W8b: tabela ligi z WP w module (trasa /api/wp-tabela): para liga/sezon z powiązania ligi z WP, tryby final/live, mapowanie wierszy na pola panelu, ostrzeżenia,
wyraźne błędy (WP nie odpowiada, odrzucone logowanie, liga bez tabeli, stara wtyczka, zły format, liga spoza WP) i brak jakiegokolwiek buforowania.
Wspólne dla obu modułów: make(APP, 'futsal_nalf'|'garbarnia'). WP to atrapa HTTP (prawdziwą trasę sprawdza dry_run_w8b_wp.py)."""
import json
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import harness

ODP = {'ok': True, 'mode': 'final', 'league': 820, 'season': 819, 'criteria': 't1-nalf', 'computed_at': '2026-11-05T12:34:56+00:00', 'engine': 'SAH2H',
       'matches_counted': 6, 'live_matches': 0, 'columns': [{'klucz': 'pts', 'nazwa': 'Pts', 'etykieta': 'Pkt'}],
       'rows': [{'pos': 1, 'team_id': 7, 'name': 'Nowy Ład', 'name14': 'Nowy Ład', 'short': 'NOW', 'p': 7, 'w': 6, 'd': 1, 'l': 0, 'f': 52, 'a': 14, 'gd': 38, 'pts': 19, 'wa': 3},
                {'pos': 2, 'team_id': 8, 'name': 'Boanerges Kraków', 'name14': 'Boanerges', 'short': 'BOA', 'p': 6, 'w': 5, 'd': 1, 'l': 0, 'f': 31, 'a': 13, 'gd': 18, 'pts': 16, 'wa': 2}],
       'warnings': [{'typ': 'duplikat_meczu', 'mecz_id': 5, 'mecz': 'A - B', 'opis': 'Ta sama para występuje 2 razy.', 'wplyw': 'liczona wielokrotnie (2 razy)'}]}


class AtrapaWpTabela:
    def __init__(self):
        self.kod, self.odp = 200, dict(ODP)
        self.zapytania = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                fake.zapytania.append(q)
                raw = json.dumps(fake.odp).encode()
                self.send_response(fake.kod)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def zamknij(self):
        self.server.shutdown()
        self.server.server_close()


def make(APP, modul):
    class WpTabela(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.extensions import db
            from core.managers.wp_client import WpConfig
            from core.models.base_league_foreign_id import get_league_foreign_id_model
            from core.models.base_scraper import get_scraper_model
            self.fake = AtrapaWpTabela()
            self.wp = cm.get_wp_manager()
            self._cfg = self.wp.cfg
            self.wp.cfg = WpConfig(enabled=True, module_id='x', url=f'http://127.0.0.1:{self.fake.port}', user='u', password='p')
            sc = get_scraper_model()(name='wp', folder='wp')
            db.session.add(sc)
            db.session.commit()
            db.session.add(get_league_foreign_id_model()(scraper_id=sc.id, league_id=self.ids['league'], foreign_id='820:819'))
            db.session.commit()
            self.client = APP.test_client()
            self.lid = self.ids['league']

        def tearDown(self):
            self.wp.cfg = self._cfg
            self.fake.zamknij()
            self.ctx.pop()

        def get(self, mode='final', lid=None):
            return self.client.get(f'/api/wp-tabela?league_id={lid or self.lid}&mode={mode}')

        def test_tabela_z_wp_z_para_liga_sezon_i_polami_panelu(self):
            odp = self.get('final')
            self.assertEqual(odp.status_code, 200)
            d = odp.get_json()
            self.assertTrue(d['ok'])
            self.assertEqual({k: v for k, v in self.fake.zapytania[-1].items() if k != 'rest_route'}, {'league': '820', 'season': '819', 'mode': 'final'})     # para z powiązania ligi modułu z WP
            r = d['rows'][0]
            self.assertEqual((r['position'], r['team_name'], r['team_name_14'], r['team_short_name'], r['games'], r['wins'], r['draws'], r['loses'],
                              r['goals_scored'], r['goals_lost'], r['goal_difference'], r['points']), (1, 'Nowy Ład', 'Nowy Ład', 'NOW', 7, 6, 1, 0, 52, 14, 38, 19))
            self.assertEqual(d['rows'][1]['team_name_14'], 'Boanerges')
            self.assertEqual((d['engine'], d['matches_counted'], d['computed_at']), ('SAH2H', 6, '2026-11-05T12:34:56+00:00'))
            self.assertEqual(d['warnings'][0]['typ'], 'duplikat_meczu')                                      # ostrzeżenia z WP dochodzą do panelu bez zmian

        def test_tryb_live_idzie_do_wp_i_kazde_zadanie_to_nowe_zapytanie_bez_bufora(self):
            self.get('final')
            self.fake.odp = {**ODP, 'mode': 'live', 'live_matches': 1, 'rows': [dict(ODP['rows'][1])]}
            d = self.get('live').get_json()
            self.assertEqual(self.fake.zapytania[-1]['mode'], 'live')
            self.assertEqual((d['live_matches'], len(d['rows'])), (1, 1))
            self.get('live')
            self.assertEqual(len(self.fake.zapytania), 3)                           # trzy kliknięcia = trzy zapytania do WP

        def test_wp_nie_odpowiada_wyrazny_blad_a_ostatnia_tabela_nie_jest_pokazywana(self):
            self.assertTrue(self.get('final').get_json()['ok'])
            self.fake.zamknij()                                                     # WP zniknęło po udanym pobraniu
            odp = self.get('final')
            d = odp.get_json()
            self.assertEqual(odp.status_code, 503)
            self.assertFalse(d['ok'])
            self.assertIn('WP nie odpowiada', d['error'])
            self.assertEqual(d['kind'], 'connection')
            self.assertNotIn('rows', d)                                             # żadnej tabeli z pamięci
            self.fake = AtrapaWpTabela()                                            # dla tearDown

        def test_logowanie_odrzucone_liga_bez_tabeli_stara_wtyczka_zly_format(self):
            self.fake.kod, self.fake.odp = 401, {'code': 'rest_forbidden'}
            self.assertIn('odrzucił dane logowania', self.get().get_json()['error'])
            self.fake.kod, self.fake.odp = 404, {'code': 'bm_no_table', 'message': 'Brak tabeli'}
            odp = self.get()
            self.assertEqual(odp.status_code, 404)
            self.assertEqual(odp.get_json()['kind'], 'brak_tabeli')
            self.assertIn('nie mają tabeli', odp.get_json()['error'])
            self.fake.kod, self.fake.odp = 404, {'code': 'rest_no_route'}
            d = self.get().get_json()
            self.assertEqual(d['kind'], 'stara_wtyczka')
            self.assertIn('starej wersji', d['error'])
            self.fake.kod, self.fake.odp = 200, {'cos': 'innego'}
            d = self.get().get_json()
            self.assertEqual(d['kind'], 'format')
            self.fake.kod, self.fake.odp = 500, {'code': 'internal'}
            self.assertEqual(self.get().get_json()['kind'], 'http')

        def test_liga_spoza_wp_i_bledne_parametry(self):
            odp = self.client.get('/api/wp-tabela?league_id=9999&mode=final')
            self.assertEqual((odp.status_code, odp.get_json()['kind']), (409, 'nie_z_wp'))
            self.assertEqual(self.client.get(f'/api/wp-tabela?league_id={self.lid}&mode=zly').status_code, 400)
            self.assertEqual(self.client.get('/api/wp-tabela?mode=final').status_code, 400)
            self.assertEqual(len(self.fake.zapytania), 0)                           # błędne żądania nie dochodzą do WP

        def test_modul_bez_wp_dostaje_czytelny_blad(self):
            from core.managers.wp_client import WpConfig
            self.wp.cfg = WpConfig(enabled=False)
            odp = self.get()
            self.assertEqual((odp.status_code, odp.get_json()['kind']), (409, 'brak_wp'))

    return WpTabela


def make_node():
    """Widok tabeli z WP (prawdziwy kod wp-tabela.js w Node): wchodzi do zestawu modułu."""
    import shutil

    class WpTabelaNode(unittest.TestCase):
        def test_wp_tabela_w_node(self):
            node = shutil.which('node')
            if node is None:
                raise RuntimeError('Brak Node.js w PATH')
            skrypt = Path(__file__).resolve().parent / 'js' / 'wp_tabela_test.js'
            r = subprocess.run([node, str(skrypt)], capture_output=True, text=True, encoding='utf-8', timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('OK 5 przypadków', r.stdout)

    return WpTabelaNode
