"""E2d2: moduł zgłasza HUB-owi każdą zmianę statusu sesji i ponawia zgłoszenie po każdym połączeniu (HUB pamięta ostatni znany).

Wspólne dla obu modułów; każdy moduł ma własny plik test_status_sesji.py, który woła make(APP)."""
import json
import unittest
from unittest.mock import MagicMock, patch

import harness


def make(APP):
    class StatusSesji(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.managers.hub_client import HubClient
            self.cm = cm
            self.hub = HubClient('ws://test', app=APP)
            self.hub.connected = True
            self.hub.ws = MagicMock()
            self.hub.module_id = 'main-module'
            self._saved = cm._hub_client
            cm._hub_client = self.hub

        def tearDown(self):
            from core.extensions import db
            self.cm._hub_client = self._saved
            db.session.remove()
            self.ctx.pop()

        def _statuses(self):
            sent = [json.loads(c.args[0]) for c in self.hub.ws.send.call_args_list]
            return [m['payload'] for m in sent if m['type'] == 'session_status']

        def test_kazda_zmiana_sesji_jest_zglaszana_do_huba(self):
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            s = sm.open_session()
            self.assertEqual(self._statuses()[-1], {'state': 'preparation', 'session_id': s.id, 'game_id': None})
            PeriodManager().create_default_periods(game_id=self.ids['g1'])
            sm.activate_game(self.ids['g1'])
            self.assertEqual(self._statuses()[-1], {'state': 'preparation', 'session_id': s.id, 'game_id': self.ids['g1']})
            sm.go_on_air()
            self.assertEqual(self._statuses()[-1]['state'], 'on_air')
            sm.close_session()
            self.assertEqual(self._statuses()[-1], {'state': 'none', 'session_id': None, 'game_id': None})

        def test_wiadomosc_jest_adresowana_do_huba(self):
            import core.managers.session_manager as sm
            sm.open_session()
            msg = json.loads(self.hub.ws.send.call_args_list[-1].args[0])
            self.assertEqual((msg['to'], msg['type'], msg['from']), ('hub', 'session_status', 'main-module'))

        def test_bez_polaczenia_nic_nie_wysyla_i_nie_rzuca(self):
            import core.managers.session_manager as sm
            self.hub.connected = False
            sm.open_session()                                   # zmiana sesji nie może się wywrócić przez brak HUB-a
            self.hub.ws.send.assert_not_called()

        def test_blad_wysylki_nie_przerywa_zmiany_sesji(self):
            import core.managers.session_manager as sm
            self.hub.ws.send.side_effect = RuntimeError('zerwane')
            s = sm.open_session()
            self.assertIsNotNone(sm.get_open_session())
            self.assertEqual(sm.get_open_session().id, s.id)

        def test_brak_klienta_huba_nie_tworzy_go_przy_zmianie_sesji(self):
            import core.managers.session_manager as sm
            self.cm._hub_client = None
            sm.open_session()
            self.assertIsNone(self.cm._hub_client)

        def test_status_po_ponownym_polaczeniu_liczony_z_bazy(self):
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            PeriodManager().create_default_periods(game_id=self.ids['g1'])
            sm.activate_game(self.ids['g1'])
            sm.go_on_air()
            self.hub.ws.send.reset_mock()
            # _on_open: ponowna rejestracja, deklaracja pluginów, subskrypcja, na końcu status sesji
            self.hub.required_plugins = ['timer-plugin']
            self.hub.subscribe_classes = ['timer_update_receiver']
            with patch('time.sleep'), patch.object(self.hub, '_ensure_plugins_ready'):
                self.hub._on_open(None)
            types = [json.loads(c.args[0])['type'] for c in self.hub.ws.send.call_args_list]
            self.assertEqual(types[-1], 'session_status')
            self.assertIn('register', types)
            last = self._statuses()[-1]
            self.assertEqual((last['state'], last['game_id']), ('on_air', self.ids['g1']))

        def test_pierwsze_polaczenie_modulu_zglasza_status_wczytany_z_bazy(self):
            import core.managers.session_manager as sm
            sm.open_session()
            self.hub.ws.send.reset_mock()
            self.hub.send_session_status()                      # tak robi initialize_core_managers po subskrypcji
            self.assertEqual(self._statuses()[-1]['state'], 'preparation')

    return (StatusSesji,)
