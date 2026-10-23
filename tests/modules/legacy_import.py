"""I0: dotychczasowe pobieranie danych rozgrywek ze stron (scrapery, kadry od pomocnika, kolejka dopasowań) jest domyślnie zablokowane.

Wspólne dla obu modułów; każdy moduł ma własny plik test_legacy_import.py, który woła make(APP)."""
import re
import unittest

import harness


def make(APP):
    class BlokadaPobierania(unittest.TestCase):
        def setUp(self):
            self.client = APP.test_client()
            self._flag = APP.config.get('LEGACY_IMPORT_ENABLED')
            APP.config['LEGACY_IMPORT_ENABLED'] = False

        def tearDown(self):
            APP.config['LEGACY_IMPORT_ENABLED'] = self._flag

        def _trasy_pobierania(self):
            from core.utils.legacy_import import is_blocked_path
            wynik = []
            for rule in APP.url_map.iter_rules():
                path = re.sub(r'<(?:\w+:)?\w+>', '1', rule.rule)
                if is_blocked_path(path):
                    for method in rule.methods - {'HEAD', 'OPTIONS'}:
                        wynik.append((method, path))
            return wynik

        def test_domyslnie_wylaczone_w_konfiguracji_obu_modulow(self):
            from config import Config
            self.assertFalse(Config.LEGACY_IMPORT_ENABLED)

        def test_kazda_trasa_pobierania_zwraca_403_z_wyjasnieniem(self):
            trasy = self._trasy_pobierania()
            self.assertGreaterEqual(len(trasy), 3, 'zabezpieczenie: lista tras pobierania nie może być pusta')
            for method, path in trasy:
                r = self.client.open(path, method=method)
                self.assertEqual(r.status_code, 403, f'{method} {path}')
                self.assertIn('BM_LEGACY_IMPORT', r.get_json()['error'])

        def test_odczyt_stanu_pobierania_i_zwykle_strony_nie_sa_blokowane(self):
            self.assertNotEqual(self.client.get('/api/games/scrape/status').status_code, 403)
            self.assertEqual(self.client.get('/api/status').status_code, 200)

        def test_awaryjne_wlaczenie_zdejmuje_blokade(self):
            APP.config['LEGACY_IMPORT_ENABLED'] = True
            trasy = [t for t in self._trasy_pobierania() if t[0] == 'GET']
            self.assertTrue(trasy)
            method, path = trasy[0]
            r = self.client.open(path, method=method)
            self.assertNotEqual(r.status_code, 403)

        def test_wzorce_blokady(self):
            from core.utils.legacy_import import is_blocked_path
            for p in ('/teams/1/scrape-players', '/leagues/2/games/scrape', '/leagues/2/games/scrape-superscore', '/leagues/2/teams/scrape/superscore',
                      '/teams/3/players/pending-matches', '/players/pending-departures/4/confirm', '/helper-squad/fetch', '/api/leagues/1/scraper-data'):
                self.assertTrue(is_blocked_path(p), p)
            for p in ('/api/games/scrape/status', '/teams/', '/games/5/edit', '/wp/competitions', '/api/status'):
                self.assertFalse(is_blocked_path(p), p)

    return BlokadaPobierania
