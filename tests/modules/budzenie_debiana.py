"""E2d3a: budzenie Debiana z panelu przez HUB (dwuklik szarej ikony recorder-pluginu) i regula szarej ikony bez paska.

Wspolne dla obu modulow; kazdy modul ma wlasny plik test_budzenie_debiana.py, ktory wola make(APP)."""
import json
import time
import unittest
from unittest.mock import MagicMock, patch

import harness


def make(APP):
    class BudzenieDebiana(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.managers.hub_client import HubClient
            from core.managers.plugin_manager import PluginManager
            self.cm = cm
            self.hub = HubClient("ws://test", app=APP)
            self.hub.connected = True
            self.hub.ws = MagicMock()
            self.hub.module_id = "main-module"
            self.hub.required_plugins = ['timer-plugin', 'recorder-plugin', 'obs-ws-plugin']
            self.hub._wake_timeout_s = 0.2
            self.pm = PluginManager(self.hub)
            self.emitted = []
            self.pm._emit_to_ui = lambda t, d: self.emitted.append((t, d))
            self._saved = (cm._hub_client, cm._plugin_manager)
            cm._hub_client, cm._plugin_manager = self.hub, self.pm
            from core.extensions import socketio
            self.sio = patch.object(socketio, 'emit', side_effect=lambda t, d=None, **kw: self.emitted.append((t, d)))
            self.sio.start()

        def tearDown(self):
            from core.extensions import db
            self.sio.stop()
            if self.hub._wake_timer:
                self.hub._wake_timer.cancel()
            self.cm._hub_client, self.cm._plugin_manager = self._saved
            db.session.remove()
            self.ctx.pop()

        def _sent(self):
            return [json.loads(c.args[0]) for c in self.hub.ws.send.call_args_list]

        def _results(self):
            return [d for t, d in self.emitted if t == 'wake_host_result']

        def _hub_reply(self, payload):
            self.hub._handle_message({'type': 'wake_host_result', 'from': 'hub', 'payload': payload})

        def test_prosba_idzie_do_huba_a_nie_wprost_w_siec(self):
            self.assertTrue(self.hub.request_wake_host())
            sent = [m for m in self._sent() if m['type'] == 'wake_host']
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]['to'], 'hub')

        def test_odpowiedz_huba_trafia_do_panelu_i_nie_ma_pozniej_komunikatu_o_braku_odpowiedzi(self):
            self.hub.request_wake_host()
            self._hub_reply({'ok': True})
            time.sleep(0.4)                                   # dluzej niz czas oczekiwania na odpowiedz
            self.assertEqual(self._results(), [{'ok': True, 'error': None}])

        def test_blad_z_huba_trafia_do_panelu(self):
            self.hub.request_wake_host()
            self._hub_reply({'ok': False, 'error': 'brak adresu MAC Debiana w konfiguracji HUB-a (wol.mac)'})
            self.assertEqual(len(self._results()), 1)
            self.assertFalse(self._results()[0]['ok'])
            self.assertIn('wol.mac', self._results()[0]['error'])

        def test_hub_nie_odpowiada_panel_dostaje_czytelny_komunikat(self):
            self.hub.request_wake_host()
            time.sleep(0.5)
            res = self._results()
            self.assertEqual(len(res), 1)
            self.assertFalse(res[0]['ok'])
            self.assertIn('HUB nie odpowiedział', res[0]['error'])

        def test_brak_polaczenia_z_hubem_panel_dostaje_komunikat_od_razu_i_nic_nie_wysyla(self):
            self.hub.connected = False
            self.assertFalse(self.hub.request_wake_host())
            self.assertEqual(self._sent(), [])
            res = self._results()
            self.assertEqual(len(res), 1)
            self.assertFalse(res[0]['ok'])
            self.assertIn('Brak połączenia z HUB-em', res[0]['error'])

        def test_zdarzenie_panelu_bez_klienta_huba_daje_komunikat(self):
            from core.extensions import socketio
            client = socketio.test_client(APP)
            self.cm._hub_client = None
            self.emitted.clear()
            client.emit('wake_recorder_plugin')
            client.disconnect()
            res = self._results()
            self.assertEqual(len(res), 1)
            self.assertFalse(res[0]['ok'])

        # Regula z koncepcji (punkt 16, L1) i z E2c: recorder, ktory sie nie zglosil (Debian jeszcze nie wstal),
        # ma szara ikone i nie daje paska, takze po prosbie o budzenie i przy automatycznym odpytywaniu.
        def test_recorder_ktory_sie_nie_zglosil_po_budzeniu_ma_szara_ikone_bez_paska(self):
            self.hub.request_wake_host()
            self._hub_reply({'ok': True})
            self.hub._handle_message({'type': 'health_status', 'from': 'hub', 'payload': {
                'connected_plugins': {'timer-plugin': {'is_active': True}}, 'plugin_health': {}}})
            for _ in range(3):
                self.assertFalse(self.hub.send_to_plugin('recorder-plugin', 'recording_status', {}))
            states = [d for t, d in self.emitted if t == 'plugins_states']
            self.assertTrue(states)
            rec = states[-1]['recorder-plugin']
            self.assertFalse(rec['is_active'])                 # szara ikona
            self.assertFalse(rec['unreachable'])
            self.assertEqual([d for t, d in self.emitted if t == 'plugin_unreachable'], [])

    return BudzenieDebiana
