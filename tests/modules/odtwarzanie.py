"""E2e: odtwarzanie po awarii. Stan sesji (recovery_state) aktualizowany pojedynczymi kluczami pod blokadą, widoczny kontener nakładki
(dane z bazy przy ponownym wysłaniu), ścieżki nagrań OBS zachowane także po awarii OBS, przywrócenie sceny programu po powrocie OBS,
panel bez połączenia nie wysyła akcji (Node), szybsze ponawianie połączenia modułu z HUB-em.

Wspólne dla obu modułów; każdy moduł ma własny plik test_odtwarzanie.py, który woła make(APP)."""
import json
import pathlib
import shutil
import subprocess
import threading
import unittest
from unittest.mock import MagicMock, patch

import harness

REPO = pathlib.Path(__file__).resolve().parents[2]


def make(APP):
    class Odtwarzanie(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.managers.hub_client import HubClient
            from core.managers.service_notices import ServiceNotices
            from core.managers.period_manager import PeriodManager
            from core.extensions import socketio
            import core.managers.session_manager as sm
            self.cm, self.sm = cm, sm
            self.hub = HubClient('ws://test', app=APP)
            self.hub.connected = True
            self.hub.ws = MagicMock()
            self.hub.module_id = 'main-module'
            self._saved = (cm._hub_client, cm._service_notices, cm._obs_ws_manager, cm._timer_manager)
            cm._hub_client = self.hub
            self.notices = ServiceNotices()
            cm._service_notices = self.notices
            cm._obs_ws_manager = None
            self.emit_patch = patch.object(socketio, 'emit')
            self.emit = self.emit_patch.start()
            PeriodManager().create_default_periods(game_id=self.ids['g1'])
            sm.activate_game(self.ids['g1'])

        def tearDown(self):
            from core.extensions import db
            self.emit_patch.stop()
            self.cm._hub_client, self.cm._service_notices, self.cm._obs_ws_manager, self.cm._timer_manager = self._saved
            db.session.remove()
            self.ctx.pop()

        def _sent(self):
            return [json.loads(c.args[0]) for c in self.hub.ws.send.call_args_list]

        def _obs_manager(self):
            from core.managers.obs_ws_manager import ObsWsManager
            mgr = ObsWsManager(MagicMock())
            self.cm._obs_ws_manager = mgr
            return mgr

        # ── recovery_state: jeden klucz, jedna blokada ───────────────────────────────
        def test_aktualizacja_jednego_klucza_nie_rusza_pozostalych(self):
            self.sm.recovery_update('a', {'x': 1})
            self.sm.recovery_update('b', [1, 2])
            self.sm.recovery_update('a', fn=lambda old: {**old, 'y': 2})
            self.assertEqual(self.sm.recovery_get(), {'a': {'x': 1, 'y': 2}, 'b': [1, 2]})

        def test_rownolegle_zapisy_roznych_kluczy_sie_nie_gubia(self):
            errors = []

            def worker(i):
                try:
                    with APP.app_context():
                        for j in range(5):
                            self.sm.recovery_update(f'k{i}', j)
                            self.sm.recovery_update('lista', fn=lambda old, i=i, j=j: list(old or []) + [f'{i}-{j}'])
                except Exception as e:                       # pragma: no cover
                    errors.append(e)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(errors, [])
            data = self.sm.recovery_get()
            self.assertEqual([data.get(f'k{i}') for i in range(6)], [4] * 6)                 # klucze każdego wątku zachowane
            self.assertEqual(len(data['lista']), 30)                                          # żadne dopisanie do listy nie przepadło

        def test_bez_otwartej_sesji_zapis_nic_nie_robi_i_nie_rzuca(self):
            self.sm.close_session()
            self.assertIsNone(self.sm.recovery_update('a', 1))
            self.assertEqual(self.sm.recovery_get(), {})
            self.assertIsNone(self.sm.overlay_container_set('game-container'))

        def test_uszkodzony_json_nie_blokuje_zapisu(self):
            from core.extensions import db
            self.sm.get_open_session().recovery_state = '{nie json'
            db.session.commit()
            self.assertEqual(self.sm.recovery_update('a', 1), 1)
            self.assertEqual(self.sm.recovery_get(), {'a': 1})

        def test_stan_przetrwa_nowa_sesja_bazy_jak_po_restarcie_modulu(self):
            self.sm.overlay_container_set('break-container')
            from core.extensions import db
            db.session.remove()                           # jak nowy proces: nic w pamięci, tylko baza
            self.assertEqual(self.sm.overlay_container_get(), 'break-container')

        # ── widoczny kontener nakładki ──────────────────────────────────────────────
        def _overlay_msg(self, payload, typ='active_container_changed'):
            self.hub._handle_message({'type': typ, 'from': 'stream-overlay', 'to': 'main-module', 'payload': payload})

        def test_zmiana_widocznego_kontenera_jest_zapamietywana(self):
            self._overlay_msg({'container_id': 'game-container'})
            self.assertEqual(self.sm.overlay_container_get(), 'game-container')
            self._overlay_msg({'container_id': None})                         # operator schował wszystko
            self.assertIsNone(self.sm.overlay_container_get())

        def test_swieze_zaladowanie_nakladki_nie_kasuje_zapamietanego_kontenera(self):
            self._overlay_msg({'container_id': 'game-container'})
            self._overlay_msg({'container_id': None, 'reason': 'load'})       # nakładka startuje z ukrytymi kontenerami
            self.assertEqual(self.sm.overlay_container_get(), 'game-container')

        def test_prosba_nakladki_o_dane_przywraca_kontener_z_danymi_z_bazy_teraz(self):
            from core.extensions import db
            from app.models import Team, Game
            self._overlay_msg({'container_id': 'start-container'})
            game = Game.query.get(self.ids['g1'])
            Team.query.get(game.home_team_id).name = 'Nowa Nazwa Gospodarzy'    # po zapisie stanu: dane muszą być aktualne
            db.session.commit()
            self.hub.ws.send.reset_mock()
            self._overlay_msg({}, typ='request_game_data')
            shown = [m for m in self._sent() if m['type'] == 'show_overlay_container']
            self.assertEqual(len(shown), 1)
            self.assertEqual(shown[0]['to'], 'stream-overlay')
            self.assertEqual(shown[0]['payload']['container_id'], 'start-container')
            self.assertEqual(shown[0]['payload']['home_team_name'], 'Nowa Nazwa Gospodarzy')

        def test_bez_zapamietanego_kontenera_albo_po_schowaniu_nic_nie_wraca(self):
            self.hub.ws.send.reset_mock()
            self._overlay_msg({}, typ='request_game_data')
            self.assertEqual([m for m in self._sent() if m['type'] == 'show_overlay_container'], [])
            self._overlay_msg({'container_id': 'game-container'})
            self._overlay_msg({'container_id': None})
            self.hub.ws.send.reset_mock()
            self._overlay_msg({}, typ='request_game_data')
            self.assertEqual([m for m in self._sent() if m['type'] == 'show_overlay_container'], [])

        def test_kontener_wraca_tylko_do_nakladki(self):
            from core.managers.game_manager import GameManager
            self.sm.overlay_container_set('game-container')
            hub = MagicMock()
            GameManager()._restore_overlay_container(hub, 'stream-overlay')
            hub.send_to_plugin.assert_called_once()
            self.assertEqual(hub.send_to_plugin.call_args.args[0], 'stream-overlay')

        def test_blad_budowania_danych_nie_przerywa_odpowiedzi(self):
            from core.managers.game_manager import GameManager
            self.sm.overlay_container_set('shootout-container')               # mecz bez rzutów karnych: budowanie danych rzuca
            hub = MagicMock()
            GameManager()._restore_overlay_container(hub, 'stream-overlay')   # nie rzuca
            hub.send_to_plugin.assert_not_called()

        # ── ścieżki nagrań OBS ──────────────────────────────────────────────────────
        def _record_event(self, state, path=''):
            mgr = self._obs_manager()
            mgr.on_obs_event({'payload': {'eventType': 'RecordStateChanged',
                                          'eventData': {'outputState': state, 'outputPath': path}}})
            return mgr

        def test_start_i_stop_nagrania_tworza_wpis_ze_sciezka(self):
            self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', 'R:/rec/a.mkv')
            self.assertEqual([(e['path'], e['state']) for e in self.sm.record_paths_list()], [('R:/rec/a.mkv', 'recording')])
            self._record_event('OBS_WEBSOCKET_OUTPUT_STOPPED', 'R:/rec/a.mkv')
            self.assertEqual([(e['path'], e['state']) for e in self.sm.record_paths_list()], [('R:/rec/a.mkv', 'saved')])

        def test_starsze_obs_podaje_sciezke_dopiero_przy_zatrzymaniu(self):
            self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', '')
            self._record_event('OBS_WEBSOCKET_OUTPUT_STOPPED', 'R:/rec/b.mkv')
            self.assertEqual([(e['path'], e['state']) for e in self.sm.record_paths_list()], [('R:/rec/b.mkv', 'saved')])

        def test_kilka_nagran_w_sesji_to_lista_a_biezaca_sciezka_to_ostatnia(self):
            for name in ('a', 'b', 'c'):
                self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', f'R:/rec/{name}.mkv')
                self._record_event('OBS_WEBSOCKET_OUTPUT_STOPPED', f'R:/rec/{name}.mkv')
            self.assertEqual([e['path'] for e in self.sm.record_paths_list()], ['R:/rec/a.mkv', 'R:/rec/b.mkv', 'R:/rec/c.mkv'])
            self.assertEqual(self.sm.current_record_path(), 'R:/rec/c.mkv')

        def test_sesja_otwarta_w_trakcie_wdrozenia_bierze_sciezke_z_settings(self):
            from core.models.base_settings import get_settings_model
            get_settings_model().set_obs_record_filepath('R:/stare/poprzednie.mkv')
            self.assertEqual(self.sm.current_record_path(), 'R:/stare/poprzednie.mkv')

        def test_odpowiedz_na_zapytanie_o_czas_nagrania_uzywa_sciezki_z_sesji(self):
            from core.extensions import db
            from app.models import GameEvent, Event
            mgr = self._obs_manager()
            self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', 'R:/rec/mecz.mkv')
            event = Event.query.filter_by(name='Bramka').first() or Event(name='Bramka', short_name='GOL', is_reported=True)
            db.session.add(event)
            db.session.commit()
            from app.models import Period
            period = Period.query.filter_by(game_id=self.ids['g1']).first()
            ge = GameEvent(game_id=self.ids['g1'], event_id=event.id, period_id=period.id, game_time=10)
            db.session.add(ge)
            db.session.commit()
            mgr.on_obs_response({'payload': {'requestID': f'get-record-status-{ge.id}', 'responseData': {'outputDuration': 12345}}})
            db.session.refresh(ge)
            self.assertEqual((ge.video_path, ge.replay_end_time), ('R:/rec/mecz.mkv', 12345))

        def test_awaria_obs_w_trakcie_nagrania_zostawia_sciezke_jako_przerwane(self):
            mgr = self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', 'R:/rec/przerwane.mkv')
            mgr.send_obs_request_sync = MagicMock(return_value={'outputActive': False})     # po restarcie OBS nie nagrywa
            mgr._reconcile_recording()
            entries = self.sm.record_paths_list()
            self.assertEqual([(e['path'], e['state']) for e in entries], [('R:/rec/przerwane.mkv', 'interrupted')])
            self.assertEqual(self.sm.current_record_path(), 'R:/rec/przerwane.mkv')           # ścieżka dalej dostępna
            self.assertFalse(self.sm.get_open_session().obs_recording)

        def test_nagranie_ktore_trwa_mimo_utraty_polaczenia_pluginu_zostaje_nagrywane(self):
            mgr = self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', 'R:/rec/trwa.mkv')
            mgr.send_obs_request_sync = MagicMock(return_value={'outputActive': True})
            mgr._reconcile_recording()
            self.assertEqual([e['state'] for e in self.sm.record_paths_list()], ['recording'])

        def test_po_awarii_nowe_nagranie_dopisuje_sie_a_przerwane_zostaje(self):
            mgr = self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', 'R:/rec/1.mkv')
            mgr.send_obs_request_sync = MagicMock(return_value={'outputActive': False})
            mgr._reconcile_recording()
            self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', 'R:/rec/2.mkv')
            self._record_event('OBS_WEBSOCKET_OUTPUT_STOPPED', 'R:/rec/2.mkv')
            self.assertEqual([(e['path'], e['state']) for e in self.sm.record_paths_list()],
                             [('R:/rec/1.mkv', 'interrupted'), ('R:/rec/2.mkv', 'saved')])

        def test_brak_odpowiedzi_obs_nie_zmienia_wpisow(self):
            mgr = self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', 'R:/rec/x.mkv')
            mgr.send_obs_request_sync = MagicMock(return_value=None)
            mgr._reconcile_recording()
            self.assertEqual([e['state'] for e in self.sm.record_paths_list()], ['recording'])

        def test_opis_sesji_podaje_liste_nagran(self):
            self._record_event('OBS_WEBSOCKET_OUTPUT_STARTED', 'R:/rec/opis.mkv')
            self.assertEqual(self.sm.describe()['obs']['record_paths'][0]['path'], 'R:/rec/opis.mkv')

        # ── scena programu po powrocie OBS ──────────────────────────────────────────
        def _sync_threads(self):
            """Wątek uzgadniania po powrocie OBS wykonuje się od razu (test sprawdza wynik, nie współbieżność)."""
            class Inline:
                def __init__(self, target=None, args=(), kwargs=None, **_):
                    self.t, self.a, self.k = target, args, kwargs or {}

                def start(self):
                    self.t(*self.a, **self.k)
            return patch('core.managers.obs_ws_manager.threading.Thread', Inline)

        def _obs_back(self, mgr, current_scene, saved_scene='Mecz', scene_map=None):
            from core.extensions import db
            self.sm.get_open_session().obs_scene = saved_scene
            db.session.commit()
            mgr._scene_map = scene_map if scene_map is not None else {'Mecz': {}, 'Domyslna': {}, 'Przerwa': {}}
            responses = {'GetCurrentProgramScene': {'currentProgramSceneName': current_scene, 'sceneName': current_scene},
                         'GetRecordStatus': {'outputActive': False}}
            mgr.send_obs_request_sync = MagicMock(side_effect=lambda rt, data, timeout=2.0: responses.get(rt))
            mgr.set_current_program_scene = MagicMock()
            with self._sync_threads(), patch('core.managers.obs_ws_manager.time.sleep'):
                mgr._track_obs_link('disconnected')
                mgr._track_obs_link('connected')

        def test_po_awarii_obs_wraca_scena_programu_sprzed_awarii(self):
            mgr = self._obs_manager()
            self._obs_back(mgr, current_scene='Domyslna')
            mgr.set_current_program_scene.assert_called_once_with('Mecz')
            self.assertIn('obs-scene-restore', [n['key'] for n in self.notices.snapshot()])
            self.assertFalse(mgr._scene_restoring)

        def test_scena_juz_poprawna_nie_jest_przestawiana(self):
            mgr = self._obs_manager()
            self._obs_back(mgr, current_scene='Mecz')
            mgr.set_current_program_scene.assert_not_called()

        def test_restart_samego_pluginu_nie_przywraca_sceny(self):
            """Plugin wstał ponownie (OBS działał): moduł nie widział utraty połączenia z OBS, więc ręczna zmiana sceny operatora zostaje."""
            mgr = self._obs_manager()
            self.sm.get_open_session().obs_scene = 'Mecz'
            mgr.send_obs_request_sync = MagicMock(return_value={'currentProgramSceneName': 'Przerwa'})
            mgr.set_current_program_scene = MagicMock()
            with self._sync_threads():
                mgr._track_obs_link('connected')
            mgr.set_current_program_scene.assert_not_called()
            mgr.send_obs_request_sync.assert_not_called()

        def test_zdarzenia_sceny_w_trakcie_przywracania_nie_nadpisuja_zapisu(self):
            mgr = self._obs_manager()
            self.sm.get_open_session().obs_scene = 'Mecz'
            mgr._scene_restoring = True
            mgr.on_obs_event({'payload': {'eventType': 'CurrentProgramSceneChanged', 'eventData': {'sceneName': 'Domyslna'}}})
            self.assertEqual(self.sm.get_open_session().obs_scene, 'Mecz')
            mgr._scene_restoring = False
            mgr.on_obs_event({'payload': {'eventType': 'CurrentProgramSceneChanged', 'eventData': {'sceneName': 'Przerwa'}}})
            self.assertEqual(self.sm.get_open_session().obs_scene, 'Przerwa')       # po przywróceniu zmiany operatora są zapisywane

        def test_reczna_zmiana_sceny_tuz_przed_awaria_wraca_gdy_modul_dostal_zdarzenie(self):
            mgr = self._obs_manager()
            mgr.on_obs_event({'payload': {'eventType': 'CurrentProgramSceneChanged', 'eventData': {'sceneName': 'Przerwa'}}})
            self.assertEqual(self.sm.get_open_session().obs_scene, 'Przerwa')
            self._obs_back(mgr, current_scene='Domyslna', saved_scene='Przerwa')
            mgr.set_current_program_scene.assert_called_once_with('Przerwa')        # scena operatora, nie wcześniejsza

        def test_reczna_zmiana_sceny_bez_zdarzenia_przed_awaria_przywraca_poprzednia_i_informuje(self):
            """Awaria zaraz po ręcznej zmianie, zanim zdarzenie dotarło: wraca ostatnia scena, którą moduł znał (z komunikatem, jaka była po restarcie)."""
            mgr = self._obs_manager()
            self._obs_back(mgr, current_scene='Domyslna', saved_scene='Mecz')
            mgr.set_current_program_scene.assert_called_once_with('Mecz')
            text = [n['text'] for n in self.notices.snapshot() if n['key'] == 'obs-scene-restore'][0]
            self.assertIn('Mecz', text)
            self.assertIn('Domyslna', text)

        def test_nieistniejaca_scena_nie_jest_przywracana_i_jest_ostrzezenie(self):
            mgr = self._obs_manager()
            self._obs_back(mgr, current_scene='Domyslna', saved_scene='Zniknela', scene_map={'Domyslna': {}})
            mgr.set_current_program_scene.assert_not_called()
            n = [x for x in self.notices.snapshot() if x['key'] == 'obs-scene-restore'][0]
            self.assertEqual(n['level'], 'warning')

        def test_bez_otwartej_sesji_nic_nie_jest_przywracane(self):
            self.sm.close_session()
            mgr = self._obs_manager()
            mgr.send_obs_request_sync = MagicMock(return_value=None)
            mgr.set_current_program_scene = MagicMock()
            with self._sync_threads(), patch('core.managers.obs_ws_manager.time.sleep'):
                mgr._track_obs_link('disconnected')
                mgr._track_obs_link('connected')
            mgr.set_current_program_scene.assert_not_called()

        def test_brak_odpowiedzi_obs_na_pytanie_o_scene_nie_przestawia_sceny(self):
            mgr = self._obs_manager()
            self.sm.get_open_session().obs_scene = 'Mecz'
            mgr.send_obs_request_sync = MagicMock(return_value=None)
            mgr.set_current_program_scene = MagicMock()
            mgr._restore_program_scene('Mecz')
            mgr.set_current_program_scene.assert_not_called()

        # ── panel bez połączenia ────────────────────────────────────────────────────
        def test_skrypt_chroniacy_panel_przechodzi_testy_w_node(self):
            node = shutil.which('node')
            if not node:
                self.skipTest('brak Node.js w PATH')
            r = subprocess.run([node, str(REPO / 'tests' / 'modules' / 'js' / 'offline_guard_test.js')], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        def test_kazdy_szablon_z_socket_io_laduje_strazniczy_skrypt_zaraz_po_nim(self):
            import re
            templates = REPO / 'modules' / 'templates'
            checked = 0
            for path in templates.rglob('*.html'):
                text = path.read_text(encoding='utf-8')
                m = re.search(r'<script src="https://cdn\.socket\.io/[^"]+socket\.io\.min\.js"></script>\s*\n\s*(<script[^>]*>)', text)
                if '<script src="https://cdn.socket.io' not in text:
                    continue
                checked += 1
                self.assertTrue(m and 'js/core/offline-guard.js' in m.group(1), f'{path.name}: brak offline-guard.js zaraz po socket.io')
            self.assertGreaterEqual(checked, 6)

    return Odtwarzanie
