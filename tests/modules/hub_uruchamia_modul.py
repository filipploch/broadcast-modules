"""E2d1: moduł uruchamiany przez HUB (proces odłączony, wyjście prosto do pliku): logi bez dublowania wierszy,
ustawienia z HUB-a (adres HUB-a i port z zmiennych środowiskowych), łagodne zamknięcie na prośbę HUB-a.

Wspólne dla obu modułów; każdy moduł ma własny plik test_hub_uruchamia_modul.py, który woła make(APP)."""
import importlib
import json
import logging
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import harness


def make(APP):
    MODULE = APP.config['MODULE_NAME']

    class LogiPrzezHub(unittest.TestCase):
        """Moduł uruchomiony przez HUB: jedynym zapisującym do modul-<nazwa>.log jest moduł; konsola wyłączona."""

        def setUp(self):
            self.dir = Path(tempfile.mkdtemp(prefix='bm-hub-logs-'))
            os.environ['BM_LOG_RUN_DIR'] = str(self.dir)
            self.root = logging.getLogger()
            self.old_level = self.root.level
            self.old_handlers = list(self.root.handlers)

        def tearDown(self):
            for h in list(self.root.handlers):
                if getattr(h, '_bm_file', False):
                    h.close()
                    self.root.removeHandler(h)
            for h in self.old_handlers:
                if h not in self.root.handlers:
                    self.root.addHandler(h)
            self.root.setLevel(self.old_level)
            os.environ.pop('BM_LOG_RUN_DIR', None)
            os.environ.pop('BM_HUB_MANAGED', None)
            shutil.rmtree(self.dir, ignore_errors=True)

        def _setup(self):
            from core.utils.logs import setup_file_logging
            console = logging.StreamHandler()
            self.root.addHandler(console)
            path = setup_file_logging(MODULE, testing=False)
            return path, console

        def test_pod_kontrola_huba_konsola_wylaczona_a_wiersz_jest_raz_w_pliku(self):
            os.environ['BM_HUB_MANAGED'] = '1'
            path, console = self._setup()
            self.assertEqual(path, self.dir / f'modul-{MODULE}.log')      # folder z HUB-a, bez własnego
            self.assertNotIn(console, self.root.handlers)
            self.assertFalse([h for h in self.root.handlers
                              if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)])
            logging.getLogger('test').info('wiersz-testowy-E2d1')
            for h in self.root.handlers:
                h.flush()
            self.assertEqual(path.read_text(encoding='utf-8').count('wiersz-testowy-E2d1'), 1)
            self.assertEqual(sorted(p.name for p in self.dir.iterdir()), [f'modul-{MODULE}.log'])

        def test_wiersze_logu_aplikacji_nie_trafiaja_na_stderr_ani_stdout(self):
            """Domyślny uchwyt Flaska (stderr, własny format) dublował wiersze logu w pliku wyjścia procesu."""
            import contextlib
            import io
            from flask.logging import default_handler
            from core.utils.logs import quiet_flask_console
            os.environ['BM_HUB_MANAGED'] = '1'
            path, _ = self._setup()
            APP.logger.addHandler(default_handler)                 # tak Flask robi przy pierwszym użyciu app.logger
            try:
                quiet_flask_console(APP)
                self.assertNotIn(default_handler, APP.logger.handlers)
                err, out = io.StringIO(), io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                    APP.logger.info('flask-logger-E2d1')
                    logging.getLogger('app').debug('debug-E2d1')
                    logging.getLogger('hub_client').warning('ostrzezenie-E2d1')
                self.assertEqual(err.getvalue(), '')
                self.assertEqual(out.getvalue(), '')
                for h in self.root.handlers:
                    h.flush()
                text = path.read_text(encoding='utf-8')
                self.assertEqual(text.count('flask-logger-E2d1'), 1)
                self.assertEqual(text.count('ostrzezenie-E2d1'), 1)
            finally:
                APP.logger.removeHandler(default_handler)

        def test_uruchomiony_recznie_domyslny_uchwyt_flaska_zostaje(self):
            from flask.logging import default_handler
            from core.utils.logs import quiet_flask_console
            os.environ.pop('BM_HUB_MANAGED', None)
            APP.logger.addHandler(default_handler)
            try:
                quiet_flask_console(APP)
                self.assertIn(default_handler, APP.logger.handlers)
            finally:
                APP.logger.removeHandler(default_handler)

        def test_uruchomiony_recznie_konsola_zostaje(self):
            os.environ.pop('BM_HUB_MANAGED', None)
            path, console = self._setup()
            self.assertIn(console, self.root.handlers)

    class UstawieniaZHuba(unittest.TestCase):
        def _config(self, env):
            import config as cfg_mod
            with patch.dict(os.environ, env):
                importlib.reload(cfg_mod)
                cfg = cfg_mod.config['development']
                return cfg.HUB_HOST, cfg.APP_PORT

        def tearDown(self):
            import config as cfg_mod
            importlib.reload(cfg_mod)

        def test_domyslne_wartosci_bez_zmiennych(self):
            env = {k: v for k, v in os.environ.items() if k not in ('BM_HUB_URL', 'BM_MODULE_PORT')}
            with patch.dict(os.environ, env, clear=True):
                import config as cfg_mod
                importlib.reload(cfg_mod)
                cfg = cfg_mod.config['development']
                self.assertEqual(cfg.HUB_HOST, 'ws://localhost:8080/ws')
                self.assertEqual(cfg.APP_PORT, 8081)

        def test_tryb_debug_wylaczony_tylko_pod_kontrola_huba(self):
            import config as cfg_mod
            with patch.dict(os.environ, {'BM_HUB_MANAGED': '1'}):
                importlib.reload(cfg_mod)
                self.assertFalse(cfg_mod.config['development'].DEBUG)
            env = {k: v for k, v in os.environ.items() if k != 'BM_HUB_MANAGED'}
            with patch.dict(os.environ, env, clear=True):
                importlib.reload(cfg_mod)
                self.assertTrue(cfg_mod.config['development'].DEBUG)      # uruchomiony ręcznie: jak dotąd

        def test_adres_huba_i_port_z_huba(self):
            host, port = self._config({'BM_HUB_URL': 'ws://localhost:18080/ws', 'BM_MODULE_PORT': '18081'})
            self.assertEqual(host, 'ws://localhost:18080/ws')
            self.assertEqual(port, 18081)

    class ZamkniecieNaProsbeHuba(unittest.TestCase):
        def setUp(self):
            from core.managers.hub_client import HubClient
            self.hub = HubClient('ws://test', app=APP)
            self.hub.connected = True
            self.hub.ws = MagicMock()
            self.hub.module_id = 'main-module'
            self.exited = threading.Event()
            self.code = []

            def fake_exit(code):
                self.code.append(code)
                self.exited.set()
            self.patches = [patch.object(HubClient, '_exit_process', staticmethod(fake_exit)),
                            patch('logging.shutdown')]
            for p in self.patches:
                p.start()

        def tearDown(self):
            for p in self.patches:
                p.stop()

        def _msg(self, sender):
            return json.dumps({'from': sender, 'to': 'main-module', 'type': 'shutdown_module', 'payload': {}})

        def test_prosba_od_huba_zatrzymuje_menedzery_i_konczy_proces_kodem_0(self):
            import app.managers as mgrs
            with patch.object(mgrs, 'shutdown_all_managers') as stop_all:
                self.hub._on_message(None, self._msg('hub'))
                self.assertTrue(self.exited.wait(5), 'moduł się nie zamknął')
            stop_all.assert_called_once()
            self.assertEqual(self.code, [0])

        def test_prosba_od_kogos_innego_jest_ignorowana(self):
            import app.managers as mgrs
            with patch.object(mgrs, 'shutdown_all_managers') as stop_all:
                self.hub._on_message(None, self._msg('timer-plugin'))
                self.assertFalse(self.exited.wait(0.5))
            stop_all.assert_not_called()

        def test_blad_menedzera_nie_blokuje_zamkniecia(self):
            import app.managers as mgrs
            with patch.object(mgrs, 'shutdown_all_managers', side_effect=RuntimeError('boom')):
                self.hub._on_message(None, self._msg('hub'))
                self.assertTrue(self.exited.wait(5))
            self.assertEqual(self.code, [0])

    return LogiPrzezHub, UstawieniaZHuba, ZamkniecieNaProsbeHuba
