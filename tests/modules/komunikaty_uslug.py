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

        # -- profil i zbiór scen OBS modułu (E2d3c3): żółte ostrzeżenie, czerwony błąd, zdjęcie po realizacji
        def test_ostrzezenie_profilu_obs_jest_zolte(self):
            self.notices.on_service_event('obs-profile', 'warning', 'nie przełączono OBS (trwa stream lub nagrywanie)')
            self.assertEqual(self._keys(), ['obs-profile-warning'])
            n = [x for x in self.notices.snapshot() if x['key'] == 'obs-profile-warning'][0]
            self.assertEqual((n['text'], n['level']), ('OBS: nie przełączono OBS (trwa stream lub nagrywanie)', 'warning'))

        def test_brak_profilu_w_obs_to_czerwony_blad_zastepujacy_ostrzezenie(self):
            self.notices.on_service_event('obs-profile', 'warning', 'trwa stream')
            self.notices.on_service_event('obs-profile', 'error', 'nie ma profilu "NALF" w OBS')
            self.assertEqual(self._keys(), ['obs-profile-error'])
            self.assertEqual(self._text('obs-profile-error'), 'OBS: nie ma profilu "NALF" w OBS')

        def test_zrealizowanie_wymagania_zdejmuje_ostrzezenia_profilu(self):
            self.notices.on_service_event('obs-profile', 'warning', 'trwa stream')
            self.notices.on_service_event('obs-profile', 'recovered', '')
            self.assertEqual(self._keys(), [])

        def test_ostrzezenie_profilu_nie_rusza_komunikatow_samego_obs(self):
            self.notices.on_service_event('obs', 'restarted', 'OBS')
            self.notices.on_service_event('obs-profile', 'warning', 'trwa stream')
            self.notices.on_service_event('obs-profile', 'recovered', '')
            self.assertEqual(self._keys(), ['obs-restarted'])

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
            self.assertEqual(self._last_notices_emit(), [])

        def _last_notices_emit(self):
            """Ostatnia lista rozesłana do paneli ('service_notices'); inne zdarzenia (np. 'session_state') są pomijane."""
            lists = [c.args[1] for c in self.emit.call_args_list if c.args and c.args[0] == 'service_notices']
            return lists[-1]

        def test_operator_moze_zamknac_pasek(self):
            self.notices.on_service_event('obs', 'restarted', 'OBS')
            client = self.socketio.test_client(APP)
            try:
                client.emit('dismiss_service_notice', {'key': 'obs-restarted'})
            finally:
                client.disconnect()
            self.assertEqual(self._keys(), [])
            self.assertEqual(self._last_notices_emit(), [])        # pozostałe panele dostają pustą listę

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

    class RestartNakladki(unittest.TestCase):
        """Nakładka to źródło przeglądarki w OBS: "uruchom ponownie" w panelu odświeża to źródło (przez obs-ws-plugin)."""

        def setUp(self):
            self.ctx = APP.app_context()
            self.ctx.push()
            from core.extensions import socketio
            from core.managers.hub_client import HubClient
            self.hub = HubClient('ws://test', app=APP)
            self.hub.connected = True
            self.hub.ws = MagicMock()
            self.hub.module_id = 'main-module'
            self.emit_patch = patch.object(socketio, 'emit')
            self.emit = self.emit_patch.start()
            self.mgr = MagicMock()
            self.mgr.OVERLAY_INPUT = 'Overlay'
            self.mgr_patch = patch('core.managers.get_obs_ws_manager', return_value=self.mgr)
            self.mgr_patch.start()

        def tearDown(self):
            self.mgr_patch.stop()
            self.emit_patch.stop()
            self.ctx.pop()

        def _result(self):
            import time
            for _ in range(100):
                for call in self.emit.call_args_list:
                    if call.args and call.args[0] == 'plugin_restart_result':
                        return call.args[1]
                time.sleep(0.02)
            self.fail('brak wyniku restartu nakładki')

        def test_odswieza_zrodlo_overlay_gdy_obs_dziala(self):
            self.hub.obs_running = True
            self.mgr.refresh_browser_source.return_value = {'requestType': 'PressInputPropertiesButton'}
            self.assertTrue(self.hub.request_plugin_restart('stream-overlay'))
            res = self._result()
            self.assertEqual((res['plugin_id'], res['ok']), ('stream-overlay', True))
            self.mgr.refresh_browser_source.assert_called_once_with('Overlay')
            self.hub.ws.send.assert_not_called()          # to nie jest restart procesu przez HUB

        def test_bez_obs_komunikat_zamiast_cichego_niepowodzenia(self):
            self.hub.obs_running = False
            self.assertTrue(self.hub.request_plugin_restart('stream-overlay'))
            res = self._result()
            self.assertFalse(res['ok'])
            self.assertIn('OBS nie działa', res['error'])
            self.mgr.refresh_browser_source.assert_not_called()

        def test_brak_odpowiedzi_obs_jest_bledem(self):
            self.hub.obs_running = True
            self.mgr.refresh_browser_source.return_value = None
            self.hub.request_plugin_restart('stream-overlay')
            res = self._result()
            self.assertFalse(res['ok'])
            self.assertIn('nie odpowiedział', res['error'])

        def test_inne_pluginy_nadal_przez_hub(self):
            self.assertTrue(self.hub.request_plugin_restart('timer-plugin'))
            import json
            sent = [json.loads(c.args[0]) for c in self.hub.ws.send.call_args_list]
            self.assertEqual(sent[-1]['type'], 'restart_plugin')
            self.assertEqual(sent[-1]['payload'], {'plugin_id': 'timer-plugin'})

    return (KomunikatyUslug, RestartNakladki)
