"""E1 (d): zmiany zawodnikow w garbarni korzystaja z 'biezacego okresu' (Settings, a od E1 z sesji); w przerwie nie moga
wskazywac nierozpoczetego okresu."""
import unittest
from unittest.mock import MagicMock
import harness

APP, TMP = harness.boot("garbarnia")


class ZmianyWPrzerwie(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.ctx = APP.app_context()
        self.ctx.push()
        import core.managers as cm
        from core.managers.period_manager import PeriodManager
        cm._hub_client = MagicMock()
        tm = MagicMock()
        tm.timers = {}
        cm._timer_manager = tm
        self.cm = cm
        self.pm = PeriodManager()
        self.pm.create_default_periods(game_id=self.ids['g1'])

    def tearDown(self):
        from core.extensions import db
        self.cm._hub_client = None
        self.cm._timer_manager = None
        db.session.remove()
        self.ctx.pop()

    def test_w_przerwie_zmiana_dostaje_ostatnio_zakonczony_okres(self):
        import core.managers.session_manager as sm
        from app.managers.substitution_manager import _current_period_id
        from app.models import Period
        sm.activate_game(self.ids['g1'])
        p1, p2 = Period.query.filter_by(game_id=self.ids['g1']).order_by(Period.period_order).all()
        self.pm.start_period(p1.id)
        self.pm.finish_period(p1.id)
        self.assertEqual(_current_period_id(), p1.id)
        self.assertNotEqual(_current_period_id(), p2.id)


if __name__ == "__main__":
    unittest.main()
