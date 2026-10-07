"""E1 krok 5: zegary wyliczane z okresu i GameTimer (bez Settings.current_timers), start okresu usuwa zegar poprzedniego,
przerwa miedzy okresami, rzuty karne. Kary i odtwarzanie kar: bez zmian (lista kar w danych dla timer-recovery.js pusta)."""
import unittest
from unittest.mock import MagicMock
import harness

APP, TMP = harness.boot("garbarnia")


class ZegaryBase(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.ctx = APP.app_context()
        self.ctx.push()
        import core.managers as cm
        from core.managers.period_manager import PeriodManager
        from app.managers.timer_manager import TimerManager
        self.cm = cm
        self.hub = MagicMock()
        cm._hub_client = self.hub
        self.tm = TimerManager(self.hub)
        self.tm._broadcast_penalty_state = lambda *a, **k: None
        cm._timer_manager = self.tm
        self.pm = PeriodManager()
        for g in (self.ids['g1'], self.ids['g2']):
            self.pm.create_default_periods(game_id=g)
        import core.managers.session_manager as sm
        self.sm = sm
        self.client = APP.test_client()

    def tearDown(self):
        from core.extensions import db
        self.cm._hub_client = None
        self.cm._timer_manager = None
        db.session.remove()
        self.ctx.pop()

    def periods(self, game_id):
        from app.models import Period
        return Period.query.filter_by(game_id=game_id).order_by(Period.period_order).all()

    def sent(self, action=None):
        """Polecenia wyslane do timer-pluginu: lista (akcja, timer_id)."""
        out = []
        for c in self.hub.send_to_plugin.call_args_list:
            _, act, payload = c.args[0], c.args[1], c.args[2]
            if action is None or act == action:
                out.append((act, (payload or {}).get('timer_id')))
        return out


class WyliczoneZegary(ZegaryBase):
    def test_brak_meczu_to_puste_dane(self):
        from core.managers.timer_manager import current_timers_for_game
        self.assertEqual(current_timers_for_game(), {'main': None, 'penalties': {'home': [], 'away': []}})

    def test_zegar_glowny_z_okresu_i_gametimer(self):
        from core.managers.timer_manager import current_timers_for_game
        from core.extensions import db
        from app.models import GameTimer
        self.sm.activate_game(self.ids['g1'])
        p1 = self.periods(self.ids['g1'])[0]
        main = current_timers_for_game()['main']
        self.assertEqual((main['timer_id'], main['state'], main['elapsed_time']), (p1.main_timer_name, 'idle', 0))
        self.assertEqual(main['limit'], p1.limit)
        self.assertEqual(main['metadata'], {'description': p1.description, 'period': 1, 'timer_class': 'main'})
        self.pm.set_period_status(p1.id, p1.STATUS_PENDING)                  # trwajacy okres bez rekordu GameTimer
        self.assertEqual(current_timers_for_game()['main']['state'], 'running')
        for state, elapsed in (('paused', 61000), ('limit_reached', 1200000), ('idle', 0)):
            gt = GameTimer.query.filter_by(plugin_timer_id=p1.main_timer_name).first()
            if gt is None:
                gt = GameTimer(game_id=p1.game_id, period_id=p1.id, timer_type='main', plugin_timer_id=p1.main_timer_name)
                db.session.add(gt)
            gt.state, gt.elapsed_time_ms = state, elapsed
            db.session.commit()
            main = current_timers_for_game()['main']
            self.assertEqual(main['state'], state)
            # okres niezakonczony: elapsed_time = 0 (timer-recovery.js uzyje initial_time okresu, nie surowego uplywu)
            self.assertEqual(main['elapsed_time'], 0)
            self.assertEqual(main['initial_time'], p1.initial_time)
        self.pm.set_period_status(p1.id, p1.STATUS_FINISHED)                  # zakonczony: zamrozony upyw jak dotad
        gt = GameTimer.query.filter_by(plugin_timer_id=p1.main_timer_name).first()
        gt.state, gt.elapsed_time_ms = 'paused', 754000
        db.session.commit()
        main = current_timers_for_game()['main']
        self.assertEqual((main['state'], main['elapsed_time']), ('paused', 754000))

    def test_okres_z_przesunieciem_nie_gubi_initial_time(self):
        """Regresja z proby z pluginem: w 2. polowie (initial_time 20 min) surowy upyw w 'elapsed_time' kasowalby przesuniecie."""
        from core.managers.timer_manager import current_timers_for_game
        from core.extensions import db
        from app.models import GameTimer
        self.sm.activate_game(self.ids['g1'])
        p1, p2 = self.periods(self.ids['g1'])
        p2.initial_time = 1200000
        db.session.commit()
        self.pm.set_period_status(p1.id, p1.STATUS_FINISHED)
        self.pm.set_period_status(p2.id, p2.STATUS_PENDING)
        db.session.add(GameTimer(game_id=p2.game_id, period_id=p2.id, timer_type='main', plugin_timer_id=p2.main_timer_name,
                                 state='running', elapsed_time_ms=3000))
        db.session.commit()
        main = current_timers_for_game()['main']
        recovery_initial = main.get('elapsed_time') or main.get('initial_time') or 0       # dokladnie jak timer-recovery.js
        self.assertEqual(recovery_initial, 1200000)

    def test_api_zwraca_ten_sam_ksztalt_co_dawny_json(self):
        self.sm.activate_game(self.ids['g1'])
        d = self.client.get('/api/settings').get_json()
        self.assertEqual(set(d['current_timers']), {'main', 'penalties'})
        self.assertEqual(self.client.get('/api/settings/current-timers').get_json(), d['current_timers'])
        r = self.client.post('/api/settings/current-timers/clear')
        self.assertTrue(r.get_json()['success'])
        self.assertEqual(self.client.get('/api/settings/current-timers').get_json(), d['current_timers'])   # pusta operacja

    # (a) kary: lista pusta, panel nic nie odtwarza
    def test_przeladowanie_panelu_przy_wpisach_kar_nie_tworzy_zegarow(self):
        from core.extensions import db
        from app.models import GameTimer
        self.sm.activate_game(self.ids['g1'])
        p1 = self.periods(self.ids['g1'])[0]
        for team in ('home', 'away'):
            db.session.add(GameTimer(game_id=p1.game_id, period_id=p1.id, timer_type='penalty', team=team,
                                     plugin_timer_id=f'penalty_{team}_1', limit_ms=120000, elapsed_time_ms=30000, state='running'))
        db.session.commit()
        self.hub.reset_mock()
        for url in ('/ui', '/', '/api/settings', '/api/settings/current-timers', '/game-period-choice'):
            self.client.get(url)
        self.assertEqual(self.sent('create_timer'), [])
        self.assertEqual(self.sent('ensure_timer'), [])
        d = self.client.get('/api/settings').get_json()
        self.assertEqual(d['current_timers']['penalties'], {'home': [], 'away': []})     # jak dotad: zawsze pusta


class StartOkresuUsuwaZegarPoprzedniego(ZegaryBase):
    # (b)
    def test_start_drugiego_okresu_usuwa_zegar_pierwszego_przed_utworzeniem_nowego(self):
        p1, p2 = self.periods(self.ids['g1'])
        self.pm.start_period(p1.id)
        self.pm.finish_period(p1.id)
        self.hub.reset_mock()
        self.pm.start_period(p2.id)
        msgs = self.sent()
        removed = [i for i, (a, t) in enumerate(msgs) if a == 'remove_timer' and t == p1.main_timer_name]
        created = [i for i, (a, t) in enumerate(msgs) if a == 'ensure_timer' and t == p2.main_timer_name]
        self.assertEqual(len(removed), 1)
        self.assertEqual(len(created), 1)
        self.assertLess(removed[0], created[0])                       # najpierw usuniecie, potem nowy zegar
        self.assertNotIn(('remove_timer', p2.main_timer_name), msgs)  # nie usuwamy zegara startowanego okresu
        self.assertEqual(sorted(k for k in self.tm.timers if k in (p1.main_timer_name, p2.main_timer_name)), [p2.main_timer_name])

    def test_pierwszy_okres_nie_usuwa_niczego(self):
        p1, _ = self.periods(self.ids['g1'])
        self.pm.start_period(p1.id)
        self.assertEqual(self.sent('remove_timer'), [])

    def test_nie_usuwa_zegarow_innych_meczow(self):
        p1_g1, p2_g1 = self.periods(self.ids['g1'])
        p1_g2, _ = self.periods(self.ids['g2'])
        self.pm.start_period(p1_g2.id)
        self.pm.start_period(p1_g1.id)
        self.pm.finish_period(p1_g1.id)
        self.hub.reset_mock()
        self.pm.start_period(p2_g1.id)
        self.assertNotIn(('remove_timer', p1_g2.main_timer_name), self.sent())

    def test_zakonczenie_okresu_zamraza_upyw_zegara_tego_okresu(self):
        from core.extensions import db
        from app.models import GameTimer
        p1, _ = self.periods(self.ids['g1'])
        self.pm.start_period(p1.id)
        self.tm.timers[p1.main_timer_name].update({'state': 'running', 'elapsed_time': 754000})
        db.session.add(GameTimer(game_id=p1.game_id, period_id=p1.id, timer_type='main', plugin_timer_id=p1.main_timer_name, state='running'))
        db.session.commit()
        self.pm.finish_period(p1.id)
        self.assertEqual(GameTimer.query.filter_by(plugin_timer_id=p1.main_timer_name).one().elapsed_time_ms, 754000)
        self.assertIn(('pause_timer', p1.main_timer_name), self.sent())


class PrzerwaMiedzyOkresami(ZegaryBase):
    # (d)
    def _do_przerwy(self):
        p1, p2 = self.periods(self.ids['g1'])
        self.sm.activate_game(self.ids['g1'])
        self.pm.start_period(p1.id)
        self.pm.finish_period(p1.id)
        return p1, p2

    def test_w_przerwie_biezacym_okresem_jest_ostatnio_zakonczony(self):
        """Tablica w przerwie wyglada jak przed zmiana: wskazuje zakonczony okres (dawny wskaznik po api_finish_period)."""
        from core.managers.timer_manager import current_timers_for_game
        p1, p2 = self._do_przerwy()
        self.assertEqual(self.sm.current_period_id(), p1.id)
        self.assertEqual(current_timers_for_game()['main']['timer_id'], p1.main_timer_name)
        d = self.client.get('/api/settings').get_json()
        self.assertEqual((d['current_period_id'], d['period']['id'], d['period']['status']), (p1.id, p1.id, p1.STATUS_FINISHED))
        self.assertEqual(self.client.get('/ui').status_code, 200)       # panel ladowany z zakonczonym okresem

    def test_zdarzenie_w_przerwie_nie_trafia_do_nierozpoczetego_okresu(self):
        from core.extensions import db
        from core.managers.game_event_manager import GameEventManager
        from app.models import Event, GameEvent
        p1, p2 = self._do_przerwy()
        ev = Event(name='Faul', short_name='F', is_reported=False)
        db.session.add(ev)
        db.session.commit()
        with self.assertRaises(ValueError):
            GameEventManager().record_event(game_id=self.ids['g1'], event_id=ev.id, game_time=1000)    # bez okresu: auto-wykrycie
        self.assertEqual(GameEvent.query.filter_by(period_id=p2.id).count(), 0)
        self.assertEqual(GameEvent.query.count(), 0)

    def test_po_starcie_nastepnego_okresu_wskazuje_trwajacy(self):
        p1, p2 = self._do_przerwy()
        self.pm.start_period(p2.id)
        self.assertEqual(self.sm.current_period_id(), p2.id)

    def test_po_zakonczeniu_ostatniego_okresu_wskazuje_ostatni(self):
        p1, p2 = self._do_przerwy()
        self.pm.start_period(p2.id)
        self.pm.finish_period(p2.id)
        self.assertEqual(self.sm.current_period_id(), p2.id)


class RzutyKarneIWyborMeczu(ZegaryBase):
    # (e)
    def _hub_calls(self, game_id):
        self.hub.reset_mock()
        self.client.get(f"/games/{game_id}/select-broadcast")
        return [(c[0], c.args[:2]) for c in self.hub.method_calls]

    def test_wybor_meczu_z_zakonczonym_konkursem_niczego_nie_wysyla_na_antene(self):
        from core.extensions import db
        from app.models import Shootout
        base = self._hub_calls(self.ids['g1'])                    # mecz bez konkursu
        db.session.add(Shootout(game_id=self.ids['g2'], home_team_shootouts=3, away_team_shootouts=2))
        db.session.commit()
        with_shootout = self._hub_calls(self.ids['g2'])
        self.assertEqual(with_shootout, base)                      # te same polecenia do hub/overlay, co bez konkursu
        self.assertIsNotNone(self.sm.current_shootout())           # 'pokazuje' dotyczy panelu (index, /ui, get_shootouts)


if __name__ == "__main__":
    unittest.main()
