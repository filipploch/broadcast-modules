"""E1: API sesji transmisji i reakcja na zdarzenia OBS (start streamu/nagrywania -> 'na antenie'; stop nie zamyka sesji)."""
import unittest
from unittest.mock import MagicMock
import harness

APP, TMP = harness.boot("futsal_nalf")


class ApiSesji(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.client = APP.test_client()

    def _select(self, game_id):
        self.client.get(f"/games/{game_id}/prepare-broadcast")
        self.client.get(f"/games/{game_id}/select-broadcast")

    def test_brak_sesji(self):
        self.assertEqual(self.client.get("/api/session").get_json(), {'open': False})
        r = self.client.post("/api/session/go-on-air")
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.get_json()['success'])
        self.assertEqual(self.client.post("/api/session/close").status_code, 409)

    def test_wybor_meczu_otwiera_sesje_w_przygotowaniu(self):
        self._select(self.ids['g1'])
        st = self.client.get("/api/session").get_json()
        self.assertTrue(st['open'])
        self.assertEqual(st['status'], 'preparation')
        self.assertEqual(st['game_id'], self.ids['g1'])
        self.assertIsNotNone(st['period_id'])

    def test_przycisk_reczny_na_antene_i_zamkniecie(self):
        self._select(self.ids['g1'])
        st = self.client.post("/api/session/go-on-air").get_json()['session']
        self.assertEqual(st['status'], 'on_air')
        self.assertEqual(self.client.post("/api/session/next-game").status_code, 200)   # kolejka pusta: sesja otwarta, bez meczu
        st = self.client.get("/api/session").get_json()
        self.assertTrue(st['open'])
        self.assertIsNone(st['game_id'])
        self.assertEqual(self.client.post("/api/session/close").get_json()['session'], {'open': False})
        self.assertEqual(self.client.post("/api/session/close").status_code, 409)

    def test_api_settings_zawiera_sesje_i_mecz_z_sesji(self):
        self._select(self.ids['g2'])
        d = self.client.get("/api/settings").get_json()
        self.assertEqual(d['current_game_id'], self.ids['g2'])
        self.assertEqual(d['current_season_id'], self.ids['season'])
        self.assertTrue(d['session']['open'])


class ZdarzeniaObs(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.ctx = APP.app_context()
        self.ctx.push()
        from core.managers.obs_ws_manager import ObsWsManager
        self.obs = ObsWsManager(MagicMock())
        self.obs._emit_to_ui = lambda *a, **k: None
        import core.managers.session_manager as sm
        self.sm = sm

    def tearDown(self):
        from core.extensions import db
        db.session.remove()
        self.ctx.pop()

    def _event(self, typ, **data):
        self.obs.on_obs_event({'payload': {'eventType': typ, 'eventData': data}})

    def test_start_streamu_ustawia_na_antenie_a_stop_nie_zamyka(self):
        self.sm.activate_game(self.ids['g1'])
        self._event('StreamStateChanged', outputState='OBS_WEBSOCKET_OUTPUT_STARTED')
        s = self.sm.get_open_session()
        self.assertEqual(s.status, 'on_air')
        self.assertTrue(s.obs_streaming)
        self._event('StreamStateChanged', outputState='OBS_WEBSOCKET_OUTPUT_STOPPED')
        s = self.sm.get_open_session()
        self.assertIsNotNone(s)                      # sesja nie zamyka sie sama
        self.assertEqual(s.status, 'on_air')
        self.assertFalse(s.obs_streaming)
        self.assertEqual(self.sm.current_game_id(), self.ids['g1'])

    def test_start_nagrywania_ustawia_na_antenie_i_zapisuje_sciezke(self):
        from core.models.base_settings import get_settings_model
        self.sm.activate_game(self.ids['g1'])
        self._event('RecordStateChanged', outputState='OBS_WEBSOCKET_OUTPUT_STARTED', outputPath='D:/Video/test.mkv')
        s = self.sm.get_open_session()
        self.assertEqual(s.status, 'on_air')
        self.assertTrue(s.obs_recording)
        self.assertEqual(get_settings_model().get_settings().obs_record_filepath, 'D:/Video/test.mkv')   # zostaje w Settings (do E2)

    def test_zmiana_sceny_zapisana_w_sesji(self):
        self.sm.activate_game(self.ids['g1'])
        self._event('CurrentProgramSceneChanged', sceneName='MECZ')
        self.assertEqual(self.sm.get_open_session().obs_scene, 'MECZ')

    def test_zdarzenia_obs_bez_sesji_nic_nie_zmieniaja(self):
        self._event('StreamStateChanged', outputState='OBS_WEBSOCKET_OUTPUT_STARTED')
        self._event('RecordStateChanged', outputState='OBS_WEBSOCKET_OUTPUT_STARTED', outputPath='')
        self.assertIsNone(self.sm.get_open_session())


if __name__ == "__main__":
    unittest.main()
