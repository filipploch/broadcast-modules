"""E2d3b krok 3: nadzór nad kamerami po stronie modułu. Lista kamer, które mają działać (kamera 1 zawsze), wysyłana pluginowi po każdej
rejestracji i zmianie; dziedziczenie kamer w sesji; potwierdzenie usunięcia nagrywającej kamery; paski „KAMERA N: …”;
źródła sCameraN w OBS po „kamera N działa”.

Wspólne dla obu modułów; każdy moduł ma własny plik test_kamery.py, który woła make(APP)."""
import unittest
from unittest.mock import MagicMock, patch

import harness


def make(APP):
    class Kamery(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.managers.recorder_manager import RecorderManager
            from core.managers.service_notices import ServiceNotices
            from core.extensions import socketio, db
            self.cm, self.db = cm, db
            self.hub = MagicMock()
            self.hub.send_to_plugin.return_value = True
            self.hub.plugin_online = {}
            self._saved = (cm._hub_client, cm._recorder_manager, cm._service_notices)
            cm._hub_client = self.hub
            self.notices = ServiceNotices()
            cm._service_notices = self.notices
            self.mgr = RecorderManager(self.hub)
            self.mgr.recorder_plugin_ip = '192.168.1.50'
            cm._recorder_manager = self.mgr
            self.emit_patch = patch.object(socketio, 'emit')
            self.emit = self.emit_patch.start()
            self.obs = MagicMock()
            self.obs_patch = patch('core.managers.get_obs_ws_manager', return_value=self.obs)
            self.obs_patch.start()
            from core.models.base_camera import get_camera_model
            Camera = get_camera_model()
            self.cams = []
            for i in range(1, 5):
                c = Camera(name=f'Kamera {i}', brand='Test', model='X')
                db.session.add(c)
                self.cams.append(c)
            db.session.commit()

        def tearDown(self):
            self.obs_patch.stop()
            self.emit_patch.stop()
            self.cm._hub_client, self.cm._recorder_manager, self.cm._service_notices = self._saved
            self.db.session.remove()
            self.ctx.pop()

        # -- pomocnicze
        def _assign(self, game_id, hdmis):
            from core.managers.game_camera_manager import GameCameraManager
            mgr = GameCameraManager()
            for h in hdmis:
                mgr.assign_camera_to_game(game_id=game_id, camera_id=self.cams[h - 1].id, hdmi_input=h)

        def _sets(self):
            """Polecenia set_active_cameras wysłane do recorder-pluginu: lista ładunków."""
            return [c.args[2] for c in self.hub.send_to_plugin.call_args_list
                    if c.args[0] == 'recorder-plugin' and c.args[1] == 'set_active_cameras']

        def _open_with(self, game_id, hdmis):
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            PeriodManager().create_default_periods(game_id=game_id)
            self._assign(game_id, hdmis)
            sm.activate_game(game_id)

        def _state(self, camera_id, state, wanted=True, recording=False, streaming=False, error=None):
            payload = {'camera_id': camera_id, 'state': state, 'wanted': wanted, 'recording': recording, 'streaming': streaming}
            if error:
                payload['error'] = error
            self.mgr.on_camera_state({'from': 'recorder-plugin', 'type': 'camera_state', 'payload': payload})

        def _notice_keys(self):
            return sorted(n['key'] for n in self.notices.snapshot())

        def _notice(self, key):
            return next(n for n in self.notices.snapshot() if n['key'] == key)

        # -- lista kamer, które mają działać
        def test_bez_sesji_dziala_tylko_kamera_1(self):
            self.assertEqual(self.mgr.wanted_cameras(), ['camera1'])

        def test_kamery_meczu_plus_kamera_1(self):
            self._open_with(self.ids['g1'], [1, 3])
            self.assertEqual(self.mgr.wanted_cameras(), ['camera1', 'camera3'])

        def test_kamera_1_zawsze_nawet_gdy_mecz_nie_ma_jej_w_opcjach(self):
            self._open_with(self.ids['g1'], [2])
            self.assertEqual(self.mgr.wanted_cameras(), ['camera1', 'camera2'])

        def test_rejestracja_pluginu_wysyla_pelna_liste(self):
            self.mgr.on_recorder_registered()
            sets = self._sets()
            self.assertEqual(len(sets), 1)
            self.assertEqual(sets[0], {'cameras': ['camera1'], 'stop_recording_for_removed': False})

        def test_ta_sama_lista_nie_jest_wysylana_dwa_razy_ale_po_nowej_rejestracji_tak(self):
            self.mgr.on_recorder_registered()
            self.mgr.sync_cameras()
            self.mgr.sync_cameras()
            self.assertEqual(len(self._sets()), 1)
            self.mgr.on_recorder_registered()      # restart pluginu / Debiana / HUB-a
            self.assertEqual(len(self._sets()), 2)

        def test_rozlaczony_plugin_lista_idzie_po_ponownym_polaczeniu(self):
            self.hub.send_to_plugin.return_value = False      # plugin niedostępny
            self.assertFalse(self.mgr.sync_cameras())
            self.hub.send_to_plugin.return_value = True
            self.mgr.on_recorder_registered()
            self.assertEqual(self._sets()[-1]['cameras'], ['camera1'])

        def test_zmiana_meczu_i_sesji_wysyla_nowa_liste(self):
            import core.managers.session_manager as sm
            self._open_with(self.ids['g1'], [1, 2])
            self.assertEqual(self._sets()[-1]['cameras'], ['camera1', 'camera2'])
            sm.close_session()
            self.assertEqual(self._sets()[-1]['cameras'], ['camera1'])      # bez sesji tylko kamera 1

        # -- dziedziczenie kamer w sesji
        def test_nastepny_mecz_dziedziczy_kamery_poprzedniego(self):
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            from core.managers.game_camera_manager import GameCameraManager
            self._open_with(self.ids['g1'], [1, 2, 4])
            PeriodManager().create_default_periods(game_id=self.ids['g2'])
            self._assign(self.ids['g2'], [1, 3])                 # własny wybór nowego meczu zostaje nadpisany
            sm.queue_game(self.ids['g2'])
            sm.next_game()
            got = sorted(gc.device_name for gc in GameCameraManager().get_cameras_for_game(self.ids['g2']))
            self.assertEqual(got, ['camera1', 'camera2', 'camera4'])
            self.assertEqual(self._sets()[-1]['cameras'], ['camera1', 'camera2', 'camera4'])

        def test_aktywacja_innego_meczu_tez_dziedziczy_a_operator_moze_potem_zmienic(self):
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            from core.managers.game_camera_manager import GameCameraManager
            self._open_with(self.ids['g1'], [1, 2])
            PeriodManager().create_default_periods(game_id=self.ids['g2'])
            sm.activate_game(self.ids['g2'])
            self.assertEqual(sorted(gc.device_name for gc in GameCameraManager().get_cameras_for_game(self.ids['g2'])), ['camera1', 'camera2'])
            gc2 = [gc for gc in GameCameraManager().get_cameras_for_game(self.ids['g2']) if gc.hdmi_input == 2][0]
            GameCameraManager().remove_camera_from_game(gc2.id)        # zmiana wyboru po dziedziczeniu zostaje
            self.assertEqual(sorted(gc.device_name for gc in GameCameraManager().get_cameras_for_game(self.ids['g2'])), ['camera1'])

        def test_pierwszy_mecz_nie_ma_czego_dziedziczyc(self):
            self._open_with(self.ids['g1'], [1])
            self.assertEqual(self.mgr.wanted_cameras(), ['camera1'])

        # -- zapis opcji meczu i potwierdzenie usunięcia nagrywającej kamery
        def _payload(self, hdmis, **extra):
            data = {'assigned': [{'camera_id': self.cams[h - 1].id, 'hdmi_input': h} for h in hdmis]}
            data.update(extra)
            return data

        def test_zapis_bez_kamery_1_jest_odrzucony(self):
            self._open_with(self.ids['g1'], [1, 2])
            code, body = self.mgr.check_camera_assignment(self.ids['g1'], self._payload([2, 3]))
            self.assertEqual(code, 400)
            self.assertIn('Kamera główna', body['error'])

        def test_usuniecie_nagrywajacej_kamery_wymaga_potwierdzenia(self):
            self._open_with(self.ids['g1'], [1, 2])
            self._state('camera2', 'running', recording=True)
            code, body = self.mgr.check_camera_assignment(self.ids['g1'], self._payload([1]))
            self.assertEqual(code, 409)
            self.assertEqual((body['confirm_required'], body['cameras']), (True, ['camera2']))
            self.assertIsNone(self.mgr.check_camera_assignment(self.ids['g1'], self._payload([1], confirm_stop_recording=True)))

        def test_usuniecie_kamery_ktora_nie_nagrywa_nie_pyta(self):
            self._open_with(self.ids['g1'], [1, 2])
            self._state('camera2', 'running', recording=False)
            self.assertIsNone(self.mgr.check_camera_assignment(self.ids['g1'], self._payload([1])))

        def test_potwierdzony_zapis_wysyla_liste_z_zatrzymaniem_nagrywania(self):
            self._open_with(self.ids['g1'], [1, 2])
            self.hub.send_to_plugin.reset_mock()
            self.mgr.after_camera_assignment_saved({'confirm_stop_recording': True})
            self.assertTrue(self._sets()[-1]['stop_recording_for_removed'])

        def test_zapis_przez_trase_opcji_meczu_dziala_od_razu(self):
            import core.managers.session_manager as sm
            self._open_with(self.ids['g1'], [1])
            self.hub.send_to_plugin.reset_mock()
            client = APP.test_client()
            resp = client.post('/api/assign/cameras/save', json=self._payload([1, 2, 3]))
            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
            self.assertEqual(self._sets()[-1]['cameras'], ['camera1', 'camera2', 'camera3'])

        def test_trasa_pyta_o_potwierdzenie_i_nic_nie_zmienia_bez_niego(self):
            from core.managers.game_camera_manager import GameCameraManager
            self._open_with(self.ids['g1'], [1, 2])
            self._state('camera2', 'running', recording=True)
            client = APP.test_client()
            resp = client.post('/api/assign/cameras/save', json=self._payload([1]))
            self.assertEqual(resp.status_code, 409)
            self.assertTrue(resp.get_json()['confirm_required'])
            self.assertEqual(len(GameCameraManager().get_cameras_for_game(self.ids['g1'])), 2)      # baza bez zmian
            resp = client.post('/api/assign/cameras/save', json=self._payload([1], confirm_stop_recording=True))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(len(GameCameraManager().get_cameras_for_game(self.ids['g1'])), 1)
            self.assertTrue(self._sets()[-1]['stop_recording_for_removed'])

        def test_odpowiedz_blocked_pokazuje_komunikat_w_panelu(self):
            self.mgr.on_set_active_cameras_response({'payload': {'status': 'ok', 'cameras': {}, 'blocked': ['camera2']}})
            events = [c.args for c in self.emit.call_args_list if c.args and c.args[0] == 'camera_remove_blocked']
            self.assertEqual(events[-1][1], {'cameras': ['camera2']})

        def test_odrzucenie_listy_przez_plugin_pozwala_wyslac_ja_ponownie(self):
            self.mgr.sync_cameras()
            self.mgr.on_set_active_cameras_response({'payload': {'status': 'error', 'error': 'kamera "camera9" nie ma odbioru'}})
            self.mgr.sync_cameras()
            self.assertEqual(len(self._sets()), 2)

        # -- paski "KAMERA N: ..." (tylko kamery z listy; trzy stany)
        def test_brak_obrazu_to_pasek_bledu(self):
            self._state('camera2', 'error', error='ffmpeg zakończył się')
            self.assertEqual(self._notice('camera-camera2')['text'], 'KAMERA 2: brak obrazu')
            self.assertEqual(self._notice('camera-camera2')['level'], 'error')

        def test_nagrywa_wprost_bez_podgladu_to_ostrzezenie(self):
            self._state('camera2', 'error', recording=True)
            n = self._notice('camera-camera2')
            self.assertEqual((n['text'], n['level']), ('KAMERA 2: nagrywa wprost, bez podglądu w OBS', 'warning'))

        def test_przerwa_w_nagraniu_do_nowego_segmentu(self):
            self._state('camera2', 'error', recording=True)
            self.mgr.on_recording_interrupted({'payload': {'camera_id': 'camera2', 'reason': 'feed_lost'}})
            self.assertEqual(self._notice('camera-camera2')['text'], 'KAMERA 2: przerwa w nagraniu (brak obrazu)')
            self._state('camera2', 'running', recording=True)
            self.assertEqual(self._notice('camera-camera2')['text'], 'KAMERA 2: przerwa w nagraniu (brak obrazu)')   # dopóki nie ma nowego segmentu
            self.mgr.on_segment_rotated({'payload': {'camera_id': 'camera2', 'reason': 'feed_restart', 'file_name': 'x.mkv'}})
            self.assertEqual(self._notice_keys(), [])

        def test_koniec_nagrania_zdejmuje_przerwe(self):
            self.mgr.on_recording_interrupted({'payload': {'camera_id': 'camera2', 'reason': 'feed_lost'}})
            self._state('camera2', 'error', recording=True)
            self.assertIn('camera-camera2', self._notice_keys())
            self.mgr.on_recording_stopped({'payload': {'camera_id': 'camera2'}})
            self._state('camera2', 'error', recording=False)
            self.assertEqual(self._notice('camera-camera2')['text'], 'KAMERA 2: brak obrazu')

        def test_startuje_i_dziala_nie_daja_paska(self):
            self._state('camera2', 'starting')
            self.assertEqual(self._notice_keys(), [])
            self._state('camera2', 'running')
            self.assertEqual(self._notice_keys(), [])

        def test_kamera_spoza_listy_nie_ma_paska(self):
            self._state('camera3', 'error', wanted=False)
            self.assertEqual(self._notice_keys(), [])

        def test_powrot_obrazu_zdejmuje_pasek_brak_obrazu(self):
            self._state('camera2', 'error')
            self._state('camera2', 'running')
            self.assertEqual(self._notice_keys(), [])

        def test_rozlaczenie_pluginu_zdejmuje_paski_kamer(self):
            self._state('camera2', 'error')
            self.mgr.on_recorder_disconnected()
            self.assertEqual(self._notice_keys(), [])
            self.assertEqual(self.mgr.camera_states(), {})

        def test_stan_kamer_trafia_do_paneli(self):
            self._state('camera2', 'running')
            events = [c.args for c in self.emit.call_args_list if c.args and c.args[0] == 'camera_states']
            self.assertEqual(events[-1][1]['cameras']['camera2']['state'], 'running')
            self.assertIn('camera1', events[-1][1]['wanted'])

        # -- źródła sCameraN w OBS
        def test_kamera_dziala_ustawia_url_i_odswieza_zrodlo_w_obs(self):
            self._state('camera2', 'running')
            self.obs.set_camera_stream_url.assert_called_once_with('camera2', '192.168.1.50')
            self.obs.restart_camera_stream_source.assert_called_once_with('camera2')

        def test_to_samo_dziala_nie_odswieza_drugi_raz(self):
            self._state('camera2', 'running')
            self._state('camera2', 'running', streaming=True)
            self.assertEqual(self.obs.restart_camera_stream_source.call_count, 1)

        def test_ponowny_powrot_obrazu_odswieza_zrodlo_ponownie(self):
            self._state('camera2', 'running')
            self._state('camera2', 'error')
            self._state('camera2', 'running')
            self.assertEqual(self.obs.restart_camera_stream_source.call_count, 2)

        def test_start_podgladu_srt_odswieza_zrodlo_bo_nasluch_powstal_pozniej(self):
            self._state('camera2', 'running')
            self.obs.reset_mock()
            self.mgr.on_stream_changed({'payload': {'camera_id': 'camera2', 'active': True}})
            self.obs.restart_camera_stream_source.assert_called_once_with('camera2')
            self.obs.reset_mock()
            self.mgr.on_stream_changed({'payload': {'camera_id': 'camera2', 'active': False}})
            self.obs.restart_camera_stream_source.assert_not_called()

        def test_kamera_spoza_listy_nie_rusza_zrodla(self):
            self.mgr.on_stream_changed({'payload': {'camera_id': 'camera3', 'active': True}})
            self.obs.restart_camera_stream_source.assert_not_called()

        def test_bez_adresu_pluginu_zrodlo_ustawi_sie_po_jego_zgloszeniu(self):
            self.mgr.recorder_plugin_ip = None
            self._state('camera2', 'running')
            self.obs.set_camera_stream_url.assert_not_called()
            self.mgr.on_recorder_plugin_info({'payload': {'ip': '10.0.0.7'}})
            self.obs.set_camera_stream_url.assert_called_with('camera2', '10.0.0.7')
            self.obs.restart_camera_stream_source.assert_called_with('camera2')

        def test_wylaczona_kamera_czysci_url_zrodla(self):
            self._state('camera2', 'running')
            self.obs.reset_mock()
            self._state('camera2', 'off', wanted=False)
            self.obs.set_camera_stream_url.assert_called_once_with('camera2', None)

        def test_nagrywanie_kamery_z_listy_nie_przestawia_zrodla_ale_spoza_listy_tak(self):
            self._state('camera2', 'running')
            self.obs.reset_mock()
            self.mgr.on_recording_started({'payload': {'camera_id': 'camera2', 'file_name': 'a.mkv'}})
            self.mgr.on_recording_stopped({'payload': {'camera_id': 'camera2'}})
            self.obs.set_camera_stream_url.assert_not_called()           # prowadzi nadzór kamer, nie nagrywanie
            self.mgr.on_recording_started({'payload': {'camera_id': 'camera4', 'file_name': 'b.mkv'}})
            self.obs.set_camera_stream_url.assert_called_with('camera4', '192.168.1.50')     # dawna zasada dla kamer spoza listy

        def test_plugin_wysyla_zdarzenia_przez_hub_client(self):
            """Zdarzenia pluginu docierają do nadzoru przez dispatch HubClient (nie tylko przez bezpośrednie wywołania)."""
            from core.managers.hub_client import HubClient
            hub = HubClient('ws://test', app=APP)
            hub.connected = True
            hub.ws = MagicMock()
            hub.module_id = 'main-module'
            hub._handle_message({'from': 'recorder-plugin', 'type': 'camera_state', 'to': 'main-module',
                     'payload': {'camera_id': 'camera2', 'state': 'error', 'wanted': True, 'recording': False, 'streaming': False}})
            self.assertEqual(self._notice('camera-camera2')['text'], 'KAMERA 2: brak obrazu')

    return Kamery
