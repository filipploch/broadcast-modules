"""W8a, C: reguły zmiany statusu meczu z zakładki MECZE (PATCH /api/games/<id>/status) i z formularza edycji, wspólne dla obu modułów.
1. Zakończenie meczu aktywnego w sesji z biegnącym zegarem jest odrzucone (409 i komunikat), zatrzymany zegar: dozwolone.
2. Cofnięcie na nierozpoczęty z zdarzeniami albo rozpoczętymi częściami jest odrzucone z komunikatem, jak wyczyścić mecz; mecz bez nich: dozwolone, wynik czyszczony."""
import unittest
from unittest.mock import MagicMock

import harness


def make(APP, modul):
    class ZmianaStatusu(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.extensions import db
            from core.managers.period_manager import PeriodManager
            from app.managers.timer_manager import TimerManager
            from app.models import Game, Period
            self.db, self.cm, self.Game, self.Period = db, cm, Game, Period
            cm._hub_client = MagicMock()
            self.tm = TimerManager(cm._hub_client)
            self.tm._broadcast_penalty_state = lambda *a, **k: None
            cm._timer_manager = self.tm
            self.g1, self.g2 = self.ids['g1'], self.ids['g2']
            PeriodManager().create_default_periods(game_id=self.g1)
            self.p1 = Period.query.filter_by(game_id=self.g1).order_by(Period.period_order).first()
            self.client = APP.test_client()

        def tearDown(self):
            self.cm._hub_client = None
            self.cm._timer_manager = None
            self.db.session.remove()
            self.ctx.pop()

        def patch(self, gid, status):
            return self.client.patch(f'/api/games/{gid}/status', json={'status': status})

        def status(self, gid):
            self.db.session.expire_all()
            return self.db.session.get(self.Game, gid).status

        def aktywuj(self, gid):
            import core.managers.session_manager as sm
            sm.activate_game(gid)

        # ---- reguła 1
        def test_zakonczenie_z_listy_meczu_aktywnego_z_biegnacym_zegarem_jest_odrzucone(self):
            self.aktywuj(self.g1)
            self.assertTrue(self.client.post(f'/api/period/{self.p1.id}/start').get_json()['ok'])
            self.tm.timers[self.p1.main_timer_name] = {'id': self.p1.main_timer_name, 'state': 'running', 'elapsed_time': 1000}
            odp = self.patch(self.g1, 2)
            self.assertEqual(odp.status_code, 409)
            self.assertIn('Zakończ mecz', odp.get_json()['error'])
            self.assertIn('transmitowany', odp.get_json()['error'])
            self.assertEqual(self.status(self.g1), self.Game.STATUS_PENDING)               # status bez zmian

        def test_zakonczenie_z_listy_gdy_zegar_stoi_jest_dozwolone(self):
            self.aktywuj(self.g1)
            self.client.post(f'/api/period/{self.p1.id}/start')
            self.tm.timers[self.p1.main_timer_name] = {'id': self.p1.main_timer_name, 'state': 'paused', 'elapsed_time': 1000}
            self.assertTrue(self.patch(self.g1, 2).get_json()['ok'])
            self.assertEqual(self.status(self.g1), self.Game.STATUS_FINISHED)

        def test_zakonczenie_z_listy_meczu_nietransmitowanego_jest_dozwolone(self):
            self.assertTrue(self.patch(self.g2, 2).get_json()['ok'])                      # g2 nie jest aktywny w sesji, brak zegara
            self.assertEqual(self.status(self.g2), self.Game.STATUS_FINISHED)

        def test_zakonczenie_z_listy_odrzucone_takze_w_formularzu_edycji_bez_zadnego_zapisu(self):
            self.aktywuj(self.g1)
            self.client.post(f'/api/period/{self.p1.id}/start')
            self.tm.timers[self.p1.main_timer_name] = {'id': self.p1.main_timer_name, 'state': 'running', 'elapsed_time': 1000}
            g = self.db.session.get(self.Game, self.g1)
            wynik_przed = (g.home_team_goals, g.away_team_goals)
            odp = self.client.post(f'/games/{self.g1}/edit', data={'status': '2', 'home_team_goals': '9', 'away_team_goals': '9',
                                                                   'home_team_id': str(g.home_team_id), 'away_team_id': str(g.away_team_id), 'league_id': str(g.league_id)})
            self.assertEqual(odp.status_code, 200)                                       # formularz wraca z komunikatem (bez przekierowania)
            self.assertEqual(self.status(self.g1), self.Game.STATUS_PENDING)
            g = self.db.session.get(self.Game, self.g1)
            self.db.session.refresh(g)
            self.assertEqual((g.home_team_goals, g.away_team_goals), wynik_przed)

        # ---- reguła 2
        def test_cofniecie_na_nierozpoczety_z_rozpoczeta_czescia_jest_odrzucone_z_opisem_czyszczenia(self):
            self.client.post(f'/api/period/{self.p1.id}/start')
            odp = self.patch(self.g1, 0)
            self.assertEqual(odp.status_code, 409)
            blad = odp.get_json()['error']
            self.assertIn('rozpoczęte części (1)', blad)
            self.assertIn('Resetuj', blad)
            self.assertIn('kopii', blad)
            self.assertEqual(self.status(self.g1), self.Game.STATUS_PENDING)

        def test_cofniecie_na_nierozpoczety_ze_zdarzeniem_jest_odrzucone(self):
            from app.models import Event, GameEvent
            ev = Event(name='Bramka', short_name='GOL', is_reported=True)
            self.db.session.add(ev)
            self.db.session.commit()
            self.db.session.add(GameEvent(game_id=self.g2, event_id=ev.id, period_id=self.p1.id, game_time=10))
            self.db.session.commit()
            self.patch(self.g2, 1)
            odp = self.patch(self.g2, 0)
            self.assertEqual(odp.status_code, 409)
            self.assertIn('zdarzenia (1)', odp.get_json()['error'])

        def test_cofniecie_na_nierozpoczety_meczu_bez_zdarzen_i_czesci_dziala_i_czysci_wynik(self):
            g = self.db.session.get(self.Game, self.g2)
            g.status, g.home_team_goals, g.away_team_goals = self.Game.STATUS_PENDING, 2, 1
            self.db.session.commit()
            self.assertTrue(self.patch(self.g2, 0).get_json()['ok'])
            self.db.session.expire_all()
            g = self.db.session.get(self.Game, self.g2)
            self.assertEqual((g.status, g.home_team_goals, g.away_team_goals), (self.Game.STATUS_NOT_STARTED, None, None))

        def test_przejscia_bez_regul_dzialaja_jak_dotad(self):
            for do in (1, 2, 1):
                self.assertTrue(self.patch(self.g2, do).get_json()['ok'], f'-> {do}')
                self.assertEqual(self.status(self.g2), do)
            self.assertEqual(self.patch(self.g2, 7).status_code, 400)

    return ZmianaStatusu
