"""E1: strona sterowania zegarem ('/') w przerwie pokazuje NASTEPNA czesc z zegarem tej czesci (jak dawna reguła strony),
a panel /ui zostaje na ostatnio zakonczonej czesci. Start drugiej czesci przez API przelacza obie strony."""
import json
import re
import unittest
from unittest.mock import MagicMock

import harness

APP, TMP = harness.boot("garbarnia")


class StronaSterowaniaWPrzerwie(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.ctx = APP.app_context()
        self.ctx.push()
        import core.managers as cm
        from core.managers.period_manager import PeriodManager
        from app.managers.timer_manager import TimerManager
        self.cm = cm
        cm._hub_client = MagicMock()
        tm = TimerManager(cm._hub_client)
        tm._broadcast_penalty_state = lambda *a, **k: None
        cm._timer_manager = tm
        PeriodManager().create_default_periods(game_id=self.ids['g1'])
        from app.models import Period
        self.p1, self.p2 = Period.query.filter_by(game_id=self.ids['g1']).order_by(Period.period_order).all()
        import core.managers.session_manager as sm
        sm.activate_game(self.ids['g1'])
        self.client = APP.test_client()

    def tearDown(self):
        from core.extensions import db
        self.cm._hub_client = None
        self.cm._timer_manager = None
        db.session.remove()
        self.ctx.pop()

    def _vars(self, url):
        html = self.client.get(url).get_data(as_text=True)
        per = re.search(r"var period\s*=\s*(\{.*?\});", html, re.S)
        mt = re.search(r"var main_timer\s*=\s*(\{.*?\});", html, re.S)
        return (json.loads(per.group(1)) if per else None, json.loads(mt.group(1)) if mt else None)

    def _break_after(self, how):
        self.client.post(f"/api/period/{self.p1.id}/start")
        if how == 'api':
            self.client.post(f"/api/period/{self.p1.id}/finish")
        else:
            self.client.get(f"/period/{self.p1.id}/finish")

    def test_w_przerwie_strona_pokazuje_czesc_2_po_zakonczeniu_przyciskiem_w_oknie_wyboru(self):
        self._break_after('form')
        period, timer = self._vars('/')
        self.assertEqual((period['id'], period['status']), (self.p2.id, self.p2.STATUS_NOT_STARTED))
        self.assertEqual((timer['timer_id'], timer['state']), (self.p2.main_timer_name, 'idle'))

    def test_w_przerwie_strona_pokazuje_czesc_2_po_zakonczeniu_dwuklikiem(self):
        self._break_after('api')
        period, timer = self._vars('/')
        self.assertEqual((period['id'], timer['timer_id']), (self.p2.id, self.p2.main_timer_name))
        ui_period, _ = self._vars('/ui')
        self.assertEqual((ui_period['id'], ui_period['status']), (self.p1.id, self.p1.STATUS_FINISHED))

    def test_start_drugiej_czesci_ze_strony_przelacza_obie_strony(self):
        self._break_after('form')
        period, _ = self._vars('/')
        self.assertTrue(self.client.post(f"/api/period/{period['id']}/start").get_json()['ok'])
        for url in ('/', '/ui'):
            per, _ = self._vars(url)
            self.assertEqual((per['id'], per['status']), (self.p2.id, self.p2.STATUS_PENDING), url)

    def test_przed_startem_w_trakcie_i_po_wszystkim(self):
        self.assertEqual(self._vars('/')[0]['id'], self.p1.id)
        self.client.post(f"/api/period/{self.p1.id}/start")
        self.assertEqual(self._vars('/')[0]['id'], self.p1.id)
        self.client.get(f"/period/{self.p1.id}/finish")
        self.client.post(f"/api/period/{self.p2.id}/start")
        self.client.get(f"/period/{self.p2.id}/finish")
        self.assertEqual(self._vars('/')[0]['id'], self.p2.id)


if __name__ == "__main__":
    unittest.main()
