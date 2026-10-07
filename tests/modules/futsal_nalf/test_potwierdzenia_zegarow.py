"""E1 (d): potwierdzenia z timer-pluginu znajduja okres po identyfikatorze zegara (main_timer_name), nie przez 'aktualny okres'."""
import unittest
from unittest.mock import MagicMock
import harness

APP, TMP = harness.boot("futsal_nalf")


class PotwierdzeniaZegarow(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.ctx = APP.app_context()
        self.ctx.push()
        from app.managers.timer_manager import TimerManager
        from core.managers.period_manager import PeriodManager
        self.tm = TimerManager(MagicMock())
        self.tm._broadcast_penalty_state = lambda *a, **k: None      # bez HUB-a
        for g in (self.ids['g1'], self.ids['g2']):
            PeriodManager().create_default_periods(game_id=g)

    def tearDown(self):
        from core.extensions import db
        db.session.remove()
        self.ctx.pop()

    def _first_period(self, game_id):
        from app.models import Period
        return Period.query.filter_by(game_id=game_id).order_by(Period.period_order).first()

    def _confirm(self, timer_id, limit=1200000):
        self.tm.on_timer_created({'payload': {'timer_id': timer_id, 'initial_time': 0, 'limit': limit, 'state': 'idle'}})

    def _game_timers(self):
        from app.models import GameTimer
        return GameTimer.query.all()

    def test_zegar_trafia_do_okresu_z_identyfikatora_a_nie_do_aktualnego_meczu(self):
        import core.managers.session_manager as sm
        p1 = self._first_period(self.ids['g1'])
        sm.activate_game(self.ids['g2'])                      # aktywny jest INNY mecz niz ten, do ktorego nalezy zegar
        self._confirm(p1.main_timer_name)
        gts = self._game_timers()
        self.assertEqual(len(gts), 1)
        self.assertEqual((gts[0].game_id, gts[0].period_id), (self.ids['g1'], p1.id))

    def test_zegar_trafia_do_okresu_takze_bez_otwartej_sesji(self):
        p1 = self._first_period(self.ids['g1'])
        self._confirm(p1.main_timer_name)
        gts = self._game_timers()
        self.assertEqual(len(gts), 1)
        self.assertEqual((gts[0].game_id, gts[0].period_id), (self.ids['g1'], p1.id))

    def test_potwierdzenie_nieznanego_zegara_jest_pomijane(self):
        self._confirm('zegar-ktorego-nie-ma-w-zadnym-okresie')
        self.assertEqual(self._game_timers(), [])

    def test_ponowne_potwierdzenie_aktualizuje_ten_sam_rekord(self):
        p1 = self._first_period(self.ids['g1'])
        self._confirm(p1.main_timer_name)
        self._confirm(p1.main_timer_name, limit=900000)
        gts = self._game_timers()
        self.assertEqual(len(gts), 1)
        self.assertEqual(gts[0].limit_ms, 900000)

    def test_kara_trafia_do_okresu_zegara_nadrzednego(self):
        import core.managers.session_manager as sm
        p1 = self._first_period(self.ids['g1'])
        sm.activate_game(self.ids['g2'])
        self._confirm(p1.main_timer_name)
        self.tm.timers['penalty_home_1'] = {'timer_id': 'penalty_home_1', 'parent_id': p1.main_timer_name}
        self._confirm('penalty_home_1', limit=120000)
        from app.models import GameTimer
        pen = GameTimer.query.filter_by(plugin_timer_id='penalty_home_1').one()
        self.assertEqual((pen.game_id, pen.period_id, pen.team), (self.ids['g1'], p1.id, 'home'))

    def test_kara_bez_zegara_nadrzednego_jest_pomijana(self):
        self._confirm('penalty_away_99', limit=120000)
        self.assertEqual(self._game_timers(), [])


if __name__ == "__main__":
    unittest.main()
