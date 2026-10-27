"""WP-2: połączenie modułu z jego instancją WordPressa, lista rozgrywek (pary liga + sezon) i rozgrywki domyślne modułu.

Atrapa WP (serwer HTTP w wątku) udaje trasy SportsPressa; prawdziwy WP sprawdza próba ręczna i `dry_run_wp.py`.
Wspólne dla obu modułów; każdy moduł ma własny plik test_wp_rozgrywki.py, który woła make(APP)."""
import base64
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock

import harness


class FakeWp:
    """Atrapa WP: kolekcje leagues, seasons, events; opcjonalne logowanie (Basic); strony po 100."""

    def __init__(self, user=None, password=None):
        self.leagues = [{'id': 1, 'name': 'Dywizja A', 'slug': 'dywizja-a'}, {'id': 2, 'name': 'Dywizja B', 'slug': 'dywizja-b'}]
        self.seasons = [{'id': 10, 'name': 'Jesień 2026', 'slug': 'jesien-2026'}, {'id': 11, 'name': 'Wiosna 2026', 'slug': 'wiosna-2026'}]
        self.events = []
        self.user, self.password = user, password
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                route = (q.get('rest_route') or [''])[0].strip('/')
                fake.requests.append((route, {k: v[0] for k, v in q.items()}))
                if fake.user:
                    expect = 'Basic ' + base64.b64encode(f'{fake.user}:{fake.password}'.encode()).decode()
                    if self.headers.get('Authorization') != expect:
                        return self._send(401, {'code': 'rest_forbidden'})
                elif 'future' in (q.get('status') or [''])[0]:
                    return self._send(400, {'code': 'rest_invalid_param'})
                data = {'sportspress/v2/leagues': fake.leagues, 'sportspress/v2/seasons': fake.seasons,
                        'sportspress/v2/events': fake.events}.get(route)
                if data is None:
                    return self._send(404, {'code': 'rest_no_route'})
                per = int((q.get('per_page') or ['10'])[0])
                page = int((q.get('page') or ['1'])[0])
                pages = max(1, -(-len(data) // per))
                self._send(200, data[(page - 1) * per: page * per], {'X-WP-Total': str(len(data)), 'X-WP-TotalPages': str(pages)})

            def _send(self, code, body, headers=None):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def event(self, eid, leagues, seasons, date='2026-09-05T12:00:00'):
        self.events.append({'id': eid, 'date': date, 'leagues': leagues, 'seasons': seasons})

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def make_cfg(port, user='', password=''):
    from core.managers.wp_client import WpConfig
    return WpConfig(enabled=True, module_id='nalf', port=port, url=f'http://127.0.0.1:{port}', user=user, password=password)


def make(APP):
    class WpConfigTests(unittest.TestCase):
        def setUp(self):
            self.tmp = Path(tempfile.mkdtemp(prefix='bm-wp-'))

        def _module(self, body):
            d = self.tmp / 'modul'
            d.mkdir(exist_ok=True)
            (d / 'module.json').write_text(json.dumps(body), encoding='utf-8')
            return d

        def test_blok_wp_daje_adres_i_dane_logowania_z_pliku_poza_repo(self):
            from core.managers.wp_client import load_wp_config
            d = self._module({'format': 1, 'id': 'nalf', 'wp': {'port': 8091, 'title': 'NALF'}})
            wpdir = self.tmp / 'wp-local'
            wpdir.mkdir()
            (wpdir / 'dane-api-nalf.json').write_text(json.dumps({'user': 'operator', 'password': 'abc def'}), encoding='utf-8')
            cfg = load_wp_config(d, wpdir)
            self.assertTrue(cfg.enabled)
            self.assertEqual((cfg.url, cfg.title, cfg.user, cfg.password, cfg.problem), ('http://127.0.0.1:8091', 'NALF', 'operator', 'abc def', ''))
            self.assertTrue(cfg.has_auth)

        def test_brak_pliku_logowania_to_odczyt_anonimowy_bez_bledu(self):
            from core.managers.wp_client import load_wp_config
            cfg = load_wp_config(self._module({'format': 1, 'id': 'nalf', 'wp': {'port': 8091}}), self.tmp / 'brak')
            self.assertTrue(cfg.enabled)
            self.assertFalse(cfg.has_auth)
            self.assertEqual(cfg.problem, '')

        def test_uszkodzony_plik_logowania_i_zly_port_to_problem_a_nie_wyjatek(self):
            from core.managers.wp_client import load_wp_config
            wpdir = self.tmp / 'wp-local'
            wpdir.mkdir()
            (wpdir / 'dane-api-nalf.json').write_text('{ to nie json', encoding='utf-8')
            cfg = load_wp_config(self._module({'format': 1, 'id': 'nalf', 'wp': {'port': 8091}}), wpdir)
            self.assertTrue(cfg.enabled)
            self.assertIn('nieczytelne', cfg.problem)
            cfg = load_wp_config(self._module({'format': 1, 'id': 'nalf', 'wp': {'port': 80}}), wpdir)
            self.assertFalse(cfg.enabled)
            self.assertIn('port', cfg.problem)

        def test_modul_bez_bloku_wp_jest_wylaczony_bez_problemu(self):
            from core.managers.wp_client import load_wp_config
            cfg = load_wp_config(self._module({'format': 1, 'id': 'x'}), self.tmp)
            self.assertEqual((cfg.enabled, cfg.problem), (False, ''))

        def test_prawdziwe_pliki_modulu_maja_blok_wp_z_portem(self):
            from core.managers.wp_client import load_wp_config
            cfg = load_wp_config(APP.config['MODULE_DIR'])
            self.assertTrue(cfg.enabled, cfg.problem)
            self.assertIn(cfg.port, (8091, 8092))

        def test_bm_wp_dir_z_huba_ma_pierwszenstwo(self):
            from core.managers.wp_client import default_wp_dir
            os.environ['BM_WP_DIR'] = str(self.tmp / 'inny')
            try:
                self.assertEqual(default_wp_dir(self.tmp / 'a' / 'b'), self.tmp / 'inny')
            finally:
                del os.environ['BM_WP_DIR']
            self.assertEqual(default_wp_dir(self.tmp / 'a' / 'b'), (self.tmp / 'a' / 'b').resolve().parents[1] / 'wp-local')

    class WpListTests(unittest.TestCase):
        def setUp(self):
            self.wp = FakeWp()

        def tearDown(self):
            self.wp.close()

        def _fetch(self, cfg=None):
            from core.managers.wp_client import WpClient, fetch_competitions
            return fetch_competitions(WpClient(cfg or make_cfg(self.wp.port)))

        def test_pozycja_to_para_liga_sezon_z_meczami_a_puste_kombinacje_nie_wystepuja(self):
            for i, (l, s, d) in enumerate([(1, 10, '2026-09-05T12:00:00'), (1, 10, '2026-12-12T12:00:00'), (2, 10, '2026-09-06T12:00:00'),
                                           (1, 11, '2026-03-01T12:00:00')]):
                self.wp.event(i + 1, [l], [s], d)
            res = self._fetch()
            self.assertEqual([i['key'] for i in res['items']], ['1:10', '1:11', '2:10'])    # (2, 11) nie ma meczu: nie ma pozycji
            a = res['items'][0]
            self.assertEqual((a['league_name'], a['season_name'], a['events'], a['first_date'], a['last_date']),
                             ('Dywizja A', 'Jesień 2026', 2, '2026-09-05', '2026-12-12'))
            self.assertEqual(res['unassigned'], 0)

        def test_mecze_bez_ligi_lub_sezonu_sa_liczone_osobno(self):
            self.wp.event(1, [1], [10])
            self.wp.event(2, [1], [])
            self.wp.event(3, [], [10])
            self.wp.event(4, [], [])
            res = self._fetch()
            self.assertEqual([i['key'] for i in res['items']], ['1:10'])
            self.assertEqual((res['unassigned'], res['total_events']), (3, 4))

        def test_mecz_z_kilkoma_kategoriami_liczy_sie_do_kazdej_pary(self):
            self.wp.event(1, [1, 2], [10, 11])
            keys = sorted(i['key'] for i in self._fetch()['items'])
            self.assertEqual(keys, ['1:10', '1:11', '2:10', '2:11'])

        def test_wszystkie_strony_kolekcji_sa_pobrane(self):
            for i in range(250):
                self.wp.event(i + 1, [1], [10])
            res = self._fetch()
            self.assertEqual(res['items'][0]['events'], 250)
            pages = [r for r in self.wp.requests if r[0] == 'sportspress/v2/events']
            self.assertEqual(len(pages), 3)

        def test_anonimowo_tylko_opublikowane_a_z_logowaniem_rowniez_zaplanowane(self):
            self._fetch()
            ev = [r for r in self.wp.requests if r[0] == 'sportspress/v2/events'][0][1]
            self.assertEqual(ev['status'], 'publish')
            self.wp.close()
            self.wp = FakeWp('operator', 'tajne')
            self._fetch(make_cfg(self.wp.port, 'operator', 'tajne'))
            ev = [r for r in self.wp.requests if r[0] == 'sportspress/v2/events'][0][1]
            self.assertEqual(ev['status'], 'publish,future')

        def test_bledy_maja_rodzaj(self):
            from core.managers.wp_client import WpClient, WpError, fetch_competitions
            self.wp.close()
            self.wp = FakeWp('operator', 'tajne')
            with self.assertRaises(WpError) as cm:
                fetch_competitions(WpClient(make_cfg(self.wp.port, 'operator', 'zle')))
            self.assertEqual(cm.exception.kind, 'auth')
            self.wp.close()
            with self.assertRaises(WpError) as cm:
                fetch_competitions(WpClient(make_cfg(self.wp.port)))          # nikt nie nasłuchuje
            self.assertEqual(cm.exception.kind, 'connection')

    class WpManagerTests(unittest.TestCase):
        def setUp(self):
            self.wp = FakeWp()
            self.tmp = Path(tempfile.mkdtemp(prefix='bm-wp-'))
            self.store = self.tmp / 'instance' / 'wp_rozgrywki.json'
            self.socketio = MagicMock()
            self.notices = MagicMock()
            self.keys = []
            self.notices.set.side_effect = lambda key, text, level='error': self.keys.append(('set', key, level))
            self.notices.clear.side_effect = lambda *keys: self.keys.extend(('clear', k, '') for k in keys)
            self.notices.on_service_event.side_effect = lambda sid, kind, msg: self.keys.append((kind, sid, msg))

        def tearDown(self):
            self.wp.close()

        def _mgr(self, port=None):
            from core.managers.wp_manager import WpManager
            return WpManager(make_cfg(port or self.wp.port), self.store, socketio=self.socketio, notices=self.notices)

        def _two_pairs(self):
            self.wp.event(1, [1], [10])
            self.wp.event(2, [2], [10])

        def test_kilka_rozgrywek_bez_wyboru_wymaga_wyboru_i_niczego_nie_przypisuje(self):
            self._two_pairs()
            st = self._mgr().refresh()
            self.assertTrue(st['connected'])
            self.assertEqual(len(st['items']), 2)
            self.assertIsNone(st['default'])
            self.assertTrue(st['needs_choice'])
            self.assertIn(('set', 'wp-choice', 'info'), self.keys)

        def test_jedna_rozgrywka_jest_przypisana_automatycznie_i_zapisana(self):
            self.wp.event(1, [1], [10])
            st = self._mgr().refresh()
            self.assertEqual(st['default']['key'], '1:10')
            self.assertTrue(st['default']['auto'])
            self.assertFalse(st['needs_choice'])
            again = self._mgr()                     # nowy proces modułu: ustawienie przeżywa restart
            self.assertEqual(again.state()['default']['key'], '1:10')

        def test_wybor_operatora_jest_zapisany_a_obca_para_odrzucona(self):
            self._two_pairs()
            m = self._mgr()
            m.refresh()
            self.assertEqual(m.set_default(2, 10), (True, ''))
            self.assertEqual(m.state()['default']['key'], '2:10')
            self.assertFalse(m.state()['default']['auto'])
            ok, err = m.set_default(2, 11)
            self.assertFalse(ok)
            self.assertIn('nie ma na liście', err)
            self.assertEqual(m.state()['default']['key'], '2:10')
            self.assertEqual(json.loads(self.store.read_text(encoding='utf-8'))['default']['key'], '2:10')

        def test_zapisana_para_ktorej_nie_ma_w_wp_jest_zglaszana_a_nie_podmieniana(self):
            self._two_pairs()
            m = self._mgr()
            m.refresh()
            m.set_default(2, 10)
            self.wp.events[:] = []                  # w WP zostaje tylko jedna inna rozgrywka
            self.wp.event(5, [1], [11])
            st = m.refresh()
            self.assertTrue(st['default_missing'])
            self.assertEqual(st['default']['key'], '2:10')            # bez cichej zmiany, nawet gdy jedyna na liście jest inna
            self.assertIn(('set', 'wp-default-missing', 'warning'), self.keys)

        def test_brak_polaczenia_pokazuje_ostatnia_liste_i_zolty_pasek_a_powrot_go_zdejmuje(self):
            self._two_pairs()
            m = self._mgr()
            m.refresh()
            self.wp.close()
            st = m.refresh()
            self.assertFalse(st['connected'])
            self.assertEqual(st['error_kind'], 'connection')
            self.assertTrue(st['from_cache'])
            self.assertEqual(len(st['items']), 2)
            self.assertTrue(any(k[0] == 'warning' and k[1] == 'wp-link' for k in self.keys))
            self.wp = FakeWp()
            m.client.cfg.port, m.client.cfg.url = self.wp.port, f'http://127.0.0.1:{self.wp.port}'
            self._two_pairs()
            st = m.refresh()
            self.assertTrue(st['connected'])
            self.assertFalse(st['from_cache'])
            self.assertTrue(any(k[0] == 'recovered' and k[1] == 'wp-link' for k in self.keys))

        def test_lekki_ping_wykrywa_utrate_wp_bez_pobierania_listy(self):
            self._two_pairs()
            m = self._mgr()
            m.refresh()
            n_events = len([r for r in self.wp.requests if r[0] == 'sportspress/v2/events'])
            self.assertTrue(m.check_link()['connected'])
            self.assertEqual(len([r for r in self.wp.requests if r[0] == 'sportspress/v2/events']), n_events)   # ping nie pobiera meczów
            self.wp.close()
            st = m.check_link()
            self.assertFalse(st['connected'])
            self.assertEqual(st['error_kind'], 'connection')
            self.assertTrue(st['from_cache'])
            self.assertTrue(any(k[0] == 'warning' and k[1] == 'wp-link' for k in self.keys))

        def test_pusta_instancja_to_komunikat_brak_rozgrywek(self):
            self.wp.event(1, [], [])
            st = self._mgr().refresh()
            self.assertTrue(st['no_competitions'])
            self.assertEqual(st['unassigned'], 1)
            self.assertIsNone(st['default'])

        def test_modul_bez_wp_nic_nie_robi(self):
            from core.managers.wp_client import WpConfig
            from core.managers.wp_manager import WpManager
            m = WpManager(WpConfig(), self.store, socketio=self.socketio, notices=self.notices)
            self.assertFalse(m.refresh()['enabled'])
            self.assertEqual(self.socketio.emit.call_count, 0)
            self.assertFalse(self.store.exists())

        def test_stan_do_paneli_jest_wysylany_tylko_przy_zmianie(self):
            self._two_pairs()
            m = self._mgr()
            m.refresh()
            n = self.socketio.emit.call_count
            m.refresh()
            self.assertEqual(self.socketio.emit.call_count, n)
            m.set_default(1, 10)
            self.assertEqual(self.socketio.emit.call_count, n + 1)
            self.assertEqual(self.socketio.emit.call_args[0][0], 'wp_state')

        def test_sam_czas_pobrania_listy_nie_wywoluje_wysylki_stanu(self):
            self._two_pairs()
            m = self._mgr()
            m.refresh()
            n = self.socketio.emit.call_count
            m._list['fetched_at'] = '2000-01-01T00:00:00'           # kolejne pobranie w innej sekundzie zmienia tylko ten znacznik
            m._publish()
            self.assertEqual(self.socketio.emit.call_count, n)

        def test_uszkodzony_plik_ustawien_nie_przeszkadza(self):
            self.store.parent.mkdir(parents=True)
            self.store.write_text('{ nie json', encoding='utf-8')
            self.assertIsNone(self._mgr().state()['default'])

    class WpPanelTests(unittest.TestCase):
        def setUp(self):
            import core.managers as cm
            self.cm = cm
            self._saved = cm._wp_manager
            self.wp = FakeWp()
            self.wp.event(1, [1], [10])
            self.wp.event(2, [2], [10])
            self.tmp = Path(tempfile.mkdtemp(prefix='bm-wp-'))
            from core.managers.wp_manager import WpManager
            cm._wp_manager = WpManager(make_cfg(self.wp.port), self.tmp / 'wp_rozgrywki.json')
            self.client = APP.test_client()

        def tearDown(self):
            self.cm._wp_manager = self._saved
            self.wp.close()

        def test_strona_rozgrywek_jest_dostepna_i_ma_przycisk_w_danych_wspolnych(self):
            r = self.client.get('/wp/competitions')
            self.assertEqual(r.status_code, 200)
            html = r.get_data(as_text=True)
            for needle in ('Rozgrywki z WordPressa', 'wp-refresh', 'wp-save', 'wp-competitions.js'):
                self.assertIn(needle, html)
            self.assertIn('/wp/competitions', self.client.get('/common-data/').get_data(as_text=True))

        def test_api_stanu_zwraca_liste_po_odswiezeniu(self):
            self.cm._wp_manager.refresh()
            data = self.client.get('/api/wp/state').get_json()
            self.assertTrue(data['connected'])
            self.assertEqual([i['key'] for i in data['items']], ['1:10', '2:10'])

        def test_zdarzenia_socket_io_stan_wybor_i_blad(self):
            # Klient testowy Flask-SocketIO nie dostarcza odpowiedzi w tej wersji bibliotek, więc przechwytujemy emit z handlerów
            from unittest.mock import patch
            from core.extensions import socketio
            self.cm._wp_manager.refresh()
            sc = socketio.test_client(APP)
            try:
                def odpowiedzi(*args):
                    with patch('flask_socketio.emit') as em:
                        sc.emit(*args)
                    return [(c.args[0], c.args[1]) for c in em.call_args_list]

                got = odpowiedzi('get_wp_state')
                self.assertEqual([n for n, _ in got], ['wp_state'])
                self.assertEqual(len(got[0][1]['items']), 2)
                (name, res), = odpowiedzi('wp_set_default', {'league_id': 2, 'season_id': 10})
                self.assertEqual((name, res['ok']), ('wp_result', True))
                self.assertEqual(self.cm._wp_manager.state()['default']['key'], '2:10')
                (name, res), = odpowiedzi('wp_set_default', {'league_id': 9, 'season_id': 9})
                self.assertEqual((name, res['ok']), ('wp_result', False))
                (name, res), = odpowiedzi('wp_set_default', {'league_id': 'x'})
                self.assertEqual((name, res['ok']), ('wp_result', False))
            finally:
                sc.disconnect()

    return WpConfigTests, WpListTests, WpManagerTests, WpPanelTests
