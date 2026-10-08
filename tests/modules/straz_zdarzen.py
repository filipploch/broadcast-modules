"""E2d1: polecenia zegara i zapisy meczu tylko przy otwartej sesji i aktywnym meczu (core/socketio_events/guard.py);
recording_command idzie tylko do pluginów, które go obsługują; leniwa inicjalizacja menedżerów jest chroniona blokadą.

Wspólne dla obu modułów; każdy moduł ma własny plik test_straz_zdarzen.py, który woła make(APP)."""
import json
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import harness


def make(APP):
    class StrazZdarzen(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            self.cm = cm
            self.tm = MagicMock()
            self.tm.start_timer.return_value = True
            self._saved = cm._timer_manager
            cm._timer_manager = self.tm
            from core.extensions import socketio
            self.client = socketio.test_client(APP)

        def tearDown(self):
            from core.extensions import db
            self.client.disconnect()
            self.cm._timer_manager = self._saved
            db.session.remove()
            self.ctx.pop()

        def _activate(self, game='g1'):
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            PeriodManager().create_default_periods(game_id=self.ids[game])
            sm.activate_game(self.ids[game])

        def _errors(self):
            return [e['args'][0]['message'] for e in self.client.get_received() if e['name'] == 'error']

        def test_start_zegara_bez_sesji_jest_odrzucony_z_wpisem_w_logu(self):
            from core.extensions import socketio
            with patch.object(socketio, 'emit') as emit,                     self.assertLogs('core.socketio_events.guard', level='WARNING') as logs:
                self.client.emit('timer_start', {'timer_id': 'OPPxBRO p:1'})
            self.tm.start_timer.assert_not_called()
            self.assertIn('brak otwartej sesji', ' '.join(logs.output))
            # klient dostaje komunikat o odrzuceniu (tylko on, nie wszyscy)
            args, kwargs = emit.call_args
            self.assertEqual(args[0], 'error')
            self.assertIn('odrzucone', args[1]['message'])
            self.assertIn('to', kwargs)

        def test_wszystkie_polecenia_zegara_bez_sesji_sa_odrzucone(self):
            from core.socketio_events.guard import GUARDED_EVENTS
            from core.extensions import socketio
            wrapped = [n for n in GUARDED_EVENTS if getattr(socketio.server.handlers['/'].get(n), '_bm_guarded', False)]
            for must in ('timer_start', 'timer_pause', 'timer_plugin_start_timer', 'change_game_value', 'add_game_event_to_db'):
                self.assertIn(must, wrapped)
            for name in wrapped:
                self.tm.reset_mock()
                with self.assertLogs('core.socketio_events.guard', level='WARNING'):
                    self.client.emit(name, {'timer_id': 'x'})
                self.assertEqual(self.tm.method_calls, [], f'{name} dotarło do menedżera zegarów bez sesji')

        def test_z_sesja_i_meczem_polecenie_przechodzi(self):
            self._activate()
            self.client.emit('timer_start', {'timer_id': 'dowolny-zegar'})
            self.tm.start_timer.assert_called_once_with('dowolny-zegar')
            self.assertEqual(self._errors(), [])

        def test_sesja_bez_aktywnego_meczu_odrzuca_polecenia(self):
            import core.managers.session_manager as sm
            sm.open_session()
            with self.assertLogs('core.socketio_events.guard', level='WARNING') as logs:
                self.client.emit('timer_start', {'timer_id': 'x'})
            self.tm.start_timer.assert_not_called()
            self.assertIn('aktywnego meczu', ' '.join(logs.output))

        def test_zegar_glowny_innego_meczu_jest_odrzucony_a_wlasny_przechodzi(self):
            from core.managers.period_manager import PeriodManager
            from core.models.base_period import get_period_model
            self._activate('g1')
            PeriodManager().create_default_periods(game_id=self.ids['g2'])
            Period = get_period_model()
            obcy = Period.query.filter_by(game_id=self.ids['g2']).first().main_timer_name
            wlasny = Period.query.filter_by(game_id=self.ids['g1']).first().main_timer_name
            self.assertNotEqual(obcy, wlasny)
            with self.assertLogs('core.socketio_events.guard', level='WARNING') as logs:
                self.client.emit('timer_start', {'timer_id': obcy})
            self.tm.start_timer.assert_not_called()
            self.assertIn('innego meczu', ' '.join(logs.output))
            self.client.emit('timer_start', {'timer_id': wlasny})
            self.tm.start_timer.assert_called_once_with(wlasny)

        def test_zdarzenia_tylko_do_odczytu_nie_sa_pilnowane(self):
            from core.extensions import socketio
            for n in ('timers_get_all', 'timer_get_state', 'get_camera_assignments'):
                h = socketio.server.handlers['/'].get(n)
                if h is not None:
                    self.assertFalse(getattr(h, '_bm_guarded', False), n)

    class RecordingCommand(unittest.TestCase):
        def setUp(self):
            from core.managers.hub_client import HubClient
            self.hub = HubClient('ws://test', app=APP)
            self.hub.connected = True
            self.hub.ws = MagicMock()
            self.hub.module_id = 'main-module'

        def _targets(self):
            return [json.loads(c.args[0])['to'] for c in self.hub.ws.send.call_args_list]

        def test_zapytanie_z_panelu_idzie_tylko_do_recordera(self):
            self.hub.send_recording_command({'requestType': 'GetRecordStatus'}, plugins=('recorder-plugin',))
            self.assertEqual(self._targets(), ['recorder-plugin'])

        def test_zdarzenie_meczu_idzie_do_recordera_i_obs_nigdy_do_wszystkich(self):
            self.hub.send_recording_command({'requestType': 'GetRecordStatus'})
            self.assertEqual(sorted(self._targets()), ['obs-ws-plugin', 'recorder-plugin'])
            self.assertNotIn('broadcast', self._targets())

        def test_plugin_znany_jako_rozlaczony_jest_pomijany(self):
            self.hub.plugin_online['recorder-plugin'] = False
            self.hub.send_recording_command({'requestType': 'GetRecordStatus'}, plugins=('recorder-plugin',))
            self.assertEqual(self._targets(), [])

    class LeniwaInicjalizacja(unittest.TestCase):
        def test_rownolegle_pobranie_menedzera_tworzy_jeden_obiekt(self):
            import core.managers as cm
            import core.managers.servo_manager as servo_mod
            created = []

            class Wolny:
                def __init__(self, hub):
                    created.append(self)
                    time.sleep(0.2)             # okno wyścigu: drugi wątek zdąży wejść do getera

            saved = cm._servo_manager
            cm._servo_manager = None
            results = []

            def worker():
                with APP.app_context():
                    results.append(cm.get_servo_manager())

            try:
                with patch.object(servo_mod, 'ServoManager', Wolny), patch.object(cm, 'get_hub_client', lambda: object()):
                    threads = [threading.Thread(target=worker) for _ in range(8)]
                    for t in threads:
                        t.start()
                    for t in threads:
                        t.join(10)
            finally:
                cm._servo_manager = saved
            self.assertEqual(len(created), 1, 'powstało więcej niż jeden menedżer')
            self.assertEqual(len({id(r) for r in results}), 1)

    return StrazZdarzen, RecordingCommand, LeniwaInicjalizacja
