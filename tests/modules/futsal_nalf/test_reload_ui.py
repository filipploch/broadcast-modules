"""E1: start czesci (np. 2. polowy) przez API przeladowuje UI (zdarzenie reload_ui_dashboard), jak start z okna wyboru czesci.

Sprawdzamy wywolanie socketio.emit (klient testowy Flask-SocketIO nie odbiera rozgloszen emitowanych spoza handlera)."""
import unittest
from unittest.mock import MagicMock, patch

import harness

APP, TMP = harness.boot("futsal_nalf")


class ReloadUiPoStarcieCzesci(unittest.TestCase):
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

    def _post(self, method, url):
        """Wykonuje zadanie i zwraca (odpowiedz, liczba emisji reload_ui_dashboard)."""
        from core.extensions import socketio
        with patch.object(socketio, 'emit') as emit:
            r = getattr(self.client, method)(url)
        return r, sum(1 for c in emit.call_args_list if c.args and c.args[0] == 'reload_ui_dashboard')

    def test_start_pierwszej_czesci_przez_api_przeladowuje_ui(self):
        r, n = self._post('post', f"/api/period/{self.p1.id}/start")
        self.assertTrue(r.get_json()['ok'])
        self.assertEqual(n, 1)

    def test_start_drugiej_czesci_przez_api_przeladowuje_ui(self):
        self.client.post(f"/api/period/{self.p1.id}/start")
        self.client.post(f"/api/period/{self.p1.id}/finish")
        r, n = self._post('post', f"/api/period/{self.p2.id}/start")
        self.assertTrue(r.get_json()['ok'])
        self.assertEqual(n, 1)

    def test_nieudany_start_nie_przeladowuje_ui(self):
        r, n = self._post('post', f"/api/period/{self.p2.id}/start")          # poprzednia czesc nie zakonczona
        self.assertEqual(r.status_code, 400)
        self.assertEqual(n, 0)

    def test_start_z_okna_wyboru_czesci_nadal_przeladowuje_ui(self):
        r, n = self._post('get', f"/period/{self.p1.id}/start")
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
