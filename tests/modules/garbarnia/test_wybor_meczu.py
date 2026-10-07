"""Testy opisujace dzisiejsze zachowanie wyboru meczu do transmisji (Settings) i niezmiennik 'nowy sezon nie rusza transmisji'."""
import unittest
import harness

APP, TMP = harness.boot("garbarnia")


class WyborMeczu(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.client = APP.test_client()

    def _prepare_and_select(self, game_id):
        self.client.get(f"/games/{game_id}/prepare-broadcast")
        return self.client.get(f"/games/{game_id}/select-broadcast")

    def test_wybor_ustawia_mecz_sezon_okres_i_zegar(self):
        self._prepare_and_select(self.ids["g1"])
        with APP.app_context():
            s = harness.settings(APP)
            self.assertEqual(s.current_game_id, self.ids["g1"])
            self.assertEqual(s.current_season_id, self.ids["season"])
            self.assertIsNotNone(s.current_period_id)           # pierwszy nierozpoczety okres
            self.assertEqual(s.get_current_timers()["main"]["state"], "idle")

    def test_zmiana_meczu_czysci_stan_poprzedniego(self):
        self._prepare_and_select(self.ids["g1"])
        self._prepare_and_select(self.ids["g2"])
        with APP.app_context():
            from app.models import Period
            s = harness.settings(APP)
            self.assertEqual(s.current_game_id, self.ids["g2"])
            self.assertEqual(Period.query.get(s.current_period_id).game_id, self.ids["g2"])
            self.assertIsNone(s.current_shootout_id)

    def test_mecz_bez_okresow_nie_moze_byc_wybrany(self):
        self.client.get(f"/games/{self.ids['g1']}/select-broadcast")
        with APP.app_context():
            self.assertIsNone(harness.settings(APP).current_game_id)

    def test_nowy_sezon_bez_meczow_nie_zmienia_transmisji(self):
        """Blad 'nowy sezon bez meczow': utworzenie sezonu nie moze wplywac na aktualny mecz ani jego sezon."""
        self._prepare_and_select(self.ids["g1"])
        with APP.app_context():
            from app.models import Season
            from core.extensions import db
            db.session.add(Season(number=31, name="Wiosna 2026")); db.session.commit()
            s = harness.settings(APP)
            self.assertEqual(s.current_game_id, self.ids["g1"])
            self.assertEqual(s.current_season_id, self.ids["season"])


if __name__ == "__main__":
    unittest.main()
