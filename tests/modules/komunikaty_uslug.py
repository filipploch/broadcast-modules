"""E2d2: komunikaty usług uruchamianych przez HUB (OBS) w panelu. Po automatycznym restarcie OBS przy otwartej sesji panel pokazuje
"OBS uruchomiony ponownie — wznów stream i nagrywanie"; komunikat znika dopiero, gdy obs-ws-plugin zgłosi działający stream,
albo gdy operator go zamknie.

Wspólne dla obu modułów; każdy moduł ma własny plik test_komunikaty_uslug.py, który woła make(APP)."""
import json
import unittest
from unittest.mock import MagicMock, patch

import harness


def make(APP):
    class KomunikatyUslug(unittest.TestCase):
        def setUp(self):
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.managers.service_notices import ServiceNotices
            self.cm = cm
            self._saved = cm._service_notices
            self.notices = ServiceNotices()
            cm._service_notices = self.notices
            from core.extensions import socketio
            self.socketio = socketio
            self.emit_patch = patch.object(socketio, 'emit')
            self.emit = self.emit_patch.start()

        def tearDown(self):
            self.emit_patch.stop()
            self.cm._service_notices = self._saved
            self.ctx.pop()

        def _keys(self):
            return sorted(n['key'] for n in self.notices.snapshot())

        def _text(self, key):
            return next(n['text'] for n in self.notices.snapshot() if n['key'] == key)

        # -- treść i cykl życia komunikatu po restarcie OBS
        def test_po_restarcie_obs_pasek_wzywa_do_wznowienia_streamu_i_nagrywania(self):
            self.notices.on_service_event('obs', 'restarted', 'OBS')
            self.assertEqual(self._keys(), ['obs-restarted'])
            self.assertEqual(self._text('obs-restarted'), 'OBS uruchomiony ponownie — wznów stream i nagrywanie')
            args, _ = self.emit.call_args
            self.assertEqual(args[0], 'service_notices')
            self.assertEqual(args[1][0]['level'], 'warning')

        def test_restart_zdejmuje_wczesniejsze_bledy_obs(self):
            self.notices.on_service_event('obs', 'error', 'brak odpowiedzi po 60 s')
            self.notices.on_service_event('obs', 'gave_up', 'OBS: limit automatycznych restartów (3) wyczerpany')
            self.assertEqual(self._keys(), ['obs-error', 'obs-gave-up'])
            self.notices.on_service_event('obs', 'restarted', 'OBS')
            self.assertEqual(self._keys(), ['obs-restarted'])

        def test_pasek_zostaje_do_zgloszenia_streamu_przez_plugin(self):
            from core.managers.obs_ws_manager import ObsWsManager
            self.notices.on_service_event('obs', 'restarted', 'OBS')
            mgr = ObsWsManager(MagicMock())
            mgr._session_update('on_obs_recording_started')       # samo nagrywanie nie zdejmuje paska
            self.assertEqual(self._keys(), ['obs-restarted'])
            self.notices.on_service_event('obs', 'recovered', 'OBS')   # powrót portu też nie
            self.assertEqual(self._keys(), ['obs-restarted'])
            mgr._session_update('on_obs_stream_started')          # stream działa: pasek znika
            self.assertEqual(self._keys(), [])
            self.assertEqual(self.emit.call_args.args[1], [])

        def test_operator_moze_zamknac_pasek(self):
            self.notices.on_service_event('obs', 'restarted', 'OBS')
            client = self.socketio.test_client(APP)
            try:
                client.emit('dismiss_service_notice', {'key': 'obs-restarted'})
            finally:
                client.disconnect()
            self.assertEqual(self._keys(), [])
            self.assertEqual(self.emit.call_args.args[1], [])     # pozostałe panele dostają pustą listę

        def test_odswiezenie_strony_przywraca_komunikaty(self):
            self.notices.on_service_event('obs', 'restarted', 'OBS')
            client = self.socketio.test_client(APP)
            try:
                # odpowiedź idzie do nadawcy zdarzenia (flask_socketio.emit w obsłudze); biblioteka testowa Socket.IO w tym
                # środowisku nie przechwytuje pakietów, więc sprawdzamy wywołanie
                with patch('flask_socketio.emit') as reply:
                    client.emit('get_service_notices')
            finally:
                client.disconnect()
            args, _ = reply.call_args
            self.assertEqual(args[0], 'service_notices')
            self.assertEqual(args[1][0]['key'], 'obs-restarted')

        def test_blad_i_powrot(self):
            self.notices.on_service_event('obs', 'error', 'brak odpowiedzi po 60 s')
            self.assertEqual(self._text('obs-error'), 'OBS: brak odpowiedzi po 60 s')
            self.notices.on_service_event('obs', 'recovered', 'OBS')
            self.assertEqual(self._keys(), [])

        def test_to_samo_zdarzenie_nie_rozsyla_listy_drugi_raz(self):
            self.notices.on_service_event('obs', 'error', 'x')
            n = self.emit.call_count
            self.notices.on_service_event('obs', 'error', 'x')
            self.assertEqual(self.emit.call_count, n)

        # -- droga z HUB-a
        def _hub(self):
            from core.managers.hub_client import HubClient
            hub = HubClient('ws://test', app=APP)
            hub.connected = True
            hub.ws = MagicMock()
            hub.module_id = 'main-module'
            return hub

        def test_service_status_od_huba_pokazuje_komunikat(self):
            hub = self._hub()
            msg = {'from': 'hub', 'to': 'main-module', 'type': 'service_status',
                   'payload': {'service_id': 'obs', 'kind': 'restarted', 'message': 'OBS'}}
            hub._on_message(None, json.dumps(msg))
            self.assertEqual(self._keys(), ['obs-restarted'])

        def test_service_status_od_innego_nadawcy_jest_ignorowany(self):
            hub = self._hub()
            msg = {'from': 'timer-plugin', 'to': 'main-module', 'type': 'service_status',
                   'payload': {'service_id': 'obs', 'kind': 'restarted', 'message': 'OBS'}}
            hub._on_message(None, json.dumps(msg))
            self.assertEqual(self._keys(), [])

    return (KomunikatyUslug,)
