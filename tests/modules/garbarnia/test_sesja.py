"""Testy menedzera sesji transmisji (E1): zasady z koncepcji, pkt 9, w tym ograniczenia wymuszone przez baze."""
import unittest
import harness

APP, TMP = harness.boot("garbarnia")


class Sesja(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.ctx = APP.app_context()
        self.ctx.push()
        import core.managers.session_manager as sm
        self.sm = sm

    def tearDown(self):
        from core.extensions import db
        db.session.remove()
        self.ctx.pop()

    def _periods(self, game_id):
        from core.managers.period_manager import PeriodManager
        PeriodManager().create_default_periods(game_id=game_id)

    # -- stan podstawowy i zasada 1
    def test_brak_otwartej_sesji_to_poprawny_stan(self):
        sm = self.sm
        self.assertIsNone(sm.get_open_session())
        self.assertIsNone(sm.current_game_id())
        self.assertIsNone(sm.current_season_id())
        self.assertIsNone(sm.current_period_id())
        self.assertEqual(sm.describe(), {'open': False})

    def test_aktywacja_meczu_otwiera_sesje_w_przygotowaniu(self):
        sm = self.sm
        e = sm.activate_game(self.ids['g1'])
        self.assertEqual(sm.current_game_id(), self.ids['g1'])
        self.assertEqual(sm.get_open_session().status, 'preparation')
        self.assertEqual(e.status, 'active')

    def test_druga_otwarta_sesja_jest_odrzucona(self):
        self.sm.open_session()
        with self.assertRaises(self.sm.SessionError):
            self.sm.open_session()

    # -- ograniczenia wymuszone przez baze
    def test_baza_nie_pozwala_na_dwie_otwarte_sesje(self):
        from core.extensions import db
        from app.models import BroadcastSession
        from sqlalchemy.exc import IntegrityError
        db.session.add(BroadcastSession(status='preparation', open_slot=1))
        db.session.commit()
        db.session.add(BroadcastSession(status='preparation', open_slot=1))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_baza_nie_pozwala_na_dwa_aktywne_mecze_w_sesji(self):
        from core.extensions import db
        from app.models import SessionGame
        from sqlalchemy.exc import IntegrityError
        s = self.sm.open_session()
        db.session.add(SessionGame(session_id=s.id, game_id=self.ids['g1'], position=1, status='active', active_slot=1))
        db.session.add(SessionGame(session_id=s.id, game_id=self.ids['g2'], position=2, status='active', active_slot=1))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    # -- zmiana meczu, kolejka, "nastepny mecz"
    def test_zmiana_meczu_zwraca_poprzedni_do_kolejki(self):
        sm = self.sm
        sm.activate_game(self.ids['g1'])
        sm.activate_game(self.ids['g2'])
        from app.models import SessionGame
        by_game = {e.game_id: e for e in SessionGame.query.all()}
        self.assertEqual(by_game[self.ids['g1']].status, 'queued')
        self.assertEqual(by_game[self.ids['g2']].status, 'active')
        self.assertEqual(sm.current_game_id(), self.ids['g2'])

    def test_nastepny_mecz_nie_zamyka_sesji(self):
        sm = self.sm
        sm.activate_game(self.ids['g1'])
        sm.queue_game(self.ids['g2'])
        sm.go_on_air()
        nxt = sm.next_game()
        self.assertEqual(nxt.game_id, self.ids['g2'])
        self.assertEqual(sm.current_game_id(), self.ids['g2'])
        self.assertEqual(sm.get_open_session().status, 'on_air')
        self.assertIsNone(sm.next_game())            # kolejka pusta: sesja zostaje otwarta bez aktywnego meczu
        self.assertIsNone(sm.current_game_id())
        self.assertIsNotNone(sm.get_open_session())

    def test_nieudana_zmiana_nie_psuje_stanu(self):
        sm = self.sm
        sm.activate_game(self.ids['g1'])
        with self.assertRaises(sm.SessionError):
            sm.activate_game(99999)
        self.assertEqual(sm.current_game_id(), self.ids['g1'])

    # -- OBS i zamykanie
    def test_start_streamu_lub_nagrywania_ustawia_na_antenie(self):
        sm = self.sm
        sm.activate_game(self.ids['g1'])
        sm.on_obs_stream_started()
        s = sm.get_open_session()
        self.assertEqual(s.status, 'on_air')
        self.assertTrue(s.obs_streaming)
        self.assertIsNotNone(s.started_at)
        sm.close_session()
        sm.activate_game(self.ids['g1'])
        sm.on_obs_recording_started()
        self.assertEqual(sm.get_open_session().status, 'on_air')

    def test_zatrzymanie_streamu_nie_zamyka_sesji(self):
        sm = self.sm
        sm.activate_game(self.ids['g1'])
        sm.on_obs_stream_started()
        sm.update_obs_state(streaming=False, recording=False)
        self.assertEqual(sm.get_open_session().status, 'on_air')
        self.assertEqual(sm.current_game_id(), self.ids['g1'])

    def test_zdarzenie_obs_bez_sesji_nic_nie_robi(self):
        self.assertIsNone(self.sm.on_obs_stream_started())
        self.assertIsNone(self.sm.get_open_session())

    def test_zamkniecie_tylko_recznie_i_pozwala_na_nowa_sesje(self):
        sm = self.sm
        sm.activate_game(self.ids['g1'])
        first = sm.get_open_session().id
        sm.close_session()
        self.assertIsNone(sm.get_open_session())
        self.assertIsNone(sm.current_game_id())
        sm.activate_game(self.ids['g2'])
        self.assertNotEqual(sm.get_open_session().id, first)
        sm.close_session()
        with self.assertRaises(sm.SessionError):
            sm.close_session()                       # brak otwartej sesji

    # -- zasada 2 i 6: sezon i okres wynikaja z meczu
    def test_sezon_wynika_z_meczu_a_nowy_sezon_nic_nie_zmienia(self):
        sm = self.sm
        from app.models import Season
        from core.extensions import db
        sm.activate_game(self.ids['g1'])
        db.session.add(Season(number=31, name="Wiosna 2026"))
        db.session.commit()
        self.assertEqual(sm.current_season_id(), self.ids['season'])
        self.assertEqual(sm.current_game_id(), self.ids['g1'])

    def test_okres_wynika_ze_statusow_okresow(self):
        sm = self.sm
        from app.models import Period
        from core.extensions import db
        self._periods(self.ids['g1'])
        sm.activate_game(self.ids['g1'])
        p1, p2 = Period.query.filter_by(game_id=self.ids['g1']).order_by(Period.period_order).all()
        self.assertEqual(sm.current_period_id(), p1.id)       # nic nie ruszylo: pierwszy nierozpoczety
        p1.status = Period.STATUS_PENDING
        db.session.commit()
        self.assertEqual(sm.current_period_id(), p1.id)       # trwajacy
        p1.status = Period.STATUS_FINISHED
        db.session.commit()
        self.assertEqual(sm.current_period_id(), p1.id)       # przerwa: ostatnio zakonczony (jak dotychczasowy panel)
        p2.status = Period.STATUS_PENDING
        db.session.commit()
        self.assertEqual(sm.current_period_id(), p2.id)       # trwajacy drugi
        p2.status = Period.STATUS_FINISHED
        db.session.commit()
        self.assertEqual(sm.current_period_id(), p2.id)       # wszystkie zakonczone: ostatni

    def test_seria_rzutow_karnych_wynika_z_aktywnego_meczu(self):
        sm = self.sm
        from app.models import Shootout
        from core.extensions import db
        sm.activate_game(self.ids['g1'])
        self.assertIsNone(sm.current_shootout())
        db.session.add(Shootout(game_id=self.ids['g1']))
        db.session.commit()
        self.assertEqual(sm.current_shootout().game_id, self.ids['g1'])
        sm.activate_game(self.ids['g2'])
        self.assertIsNone(sm.current_shootout())              # inny mecz: brak serii, nic do czyszczenia


if __name__ == "__main__":
    unittest.main()
