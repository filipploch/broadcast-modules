"""E2a: awaryjne odtwarzanie zegarow przez modul (gdy timer-plugin nie ma zegara w pliku stanu).

Dane do odtwarzania (recovery_timers_for_game, /api/settings), ostrzezenie w logu przy awaryjnym tworzeniu zegara,
ustawianie upływu odtworzonego zegara i idempotentne potwierdzenie zegara kary."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import harness

APP, TMP = harness.boot("garbarnia")


class OdtwarzanieZegarow(unittest.TestCase):
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
        self.tm = TimerManager(cm._hub_client)
        self.tm._broadcast_penalty_state = lambda *a, **k: None
        cm._timer_manager = self.tm
        PeriodManager().create_default_periods(game_id=self.ids['g1'])
        from app.models import Period
        self.p1, self.p2 = Period.query.filter_by(game_id=self.ids['g1']).order_by(Period.period_order).all()
        import core.managers.session_manager as sm
        sm.activate_game(self.ids['g1'])
        self.client = APP.test_client()
        self.now = datetime.utcnow()

    def tearDown(self):
        from core.extensions import db
        self.cm._hub_client = None
        self.cm._timer_manager = None
        db.session.remove()
        self.ctx.pop()

    # -- pomocnicze
    def _start_p1(self, state, elapsed_ms, age_s):
        """Okres 1 trwa; jego zegar glowny w bazie ma podany stan i upływ zapisany `age_s` sekund temu."""
        from core.extensions import db
        from app.models import GameTimer
        self.p1.status = self.p1.STATUS_PENDING
        gt = GameTimer(game_id=self.ids['g1'], period_id=self.p1.id, timer_type=GameTimer.TYPE_MAIN,
                       plugin_timer_id=self.p1.main_timer_name, elapsed_time_ms=elapsed_ms, limit_ms=self.p1.limit,
                       state=state)
        db.session.add(gt)
        db.session.commit()
        gt.updated_at = self.now - timedelta(seconds=age_s)
        db.session.commit()
        return gt

    def _penalty(self, team, limit_ms, start_offset_ms, state='running', suffix='1'):
        from core.extensions import db
        from app.models import GameTimer
        gt = GameTimer(game_id=self.ids['g1'], period_id=self.p1.id, timer_type=GameTimer.TYPE_PENALTY, team=team,
                       plugin_timer_id=f'penalty_{team}_{suffix}', elapsed_time_ms=0, limit_ms=limit_ms,
                       state=state, start_offset_ms=start_offset_ms)
        db.session.add(gt)
        db.session.commit()
        return gt

    # -- dane do odtwarzania
    def test_trwajacy_okres_biegnacy_zegar_ma_szacowany_upływ_z_czasem_od_zapisu(self):
        from core.managers.timer_manager import recovery_timers_for_game
        self._start_p1('running', 65000, age_s=5)
        main = recovery_timers_for_game(now=self.now)['main']
        self.assertEqual(main['timer_id'], self.p1.main_timer_name)
        self.assertEqual(main['recovery_elapsed'], 70000)                     # 65 s + 5 s od ostatniego zapisu
        self.assertEqual(main['initial_time'], self.p1.initial_time)

    def test_zegar_w_pauzie_nie_dolicza_czasu_od_zapisu(self):
        from core.managers.timer_manager import recovery_timers_for_game
        self._start_p1('paused', 65000, age_s=300)
        self.assertEqual(recovery_timers_for_game(now=self.now)['main']['recovery_elapsed'], 65000)

    def test_kara_odtwarzana_jako_zegar_zalezny_z_pozostalym_czasem(self):
        from core.managers.timer_manager import recovery_timers_for_game
        self._start_p1('running', 65000, age_s=5)                              # szacunek 70 s
        self._penalty('home', limit_ms=120000, start_offset_ms=30000)          # odbyte 70-30 = 40 s, zostaje 80 s
        pen = recovery_timers_for_game(now=self.now)['penalties']['home'][0]
        self.assertEqual(pen['timer_type'], 'dependent')
        self.assertEqual(pen['parent_id'], self.p1.main_timer_name)
        self.assertEqual((pen['limit'], pen['initial_time']), (80000, 40000))
        self.assertTrue(pen['pause_at_limit'])
        self.assertEqual(pen['state'], 'running')

    def test_kara_odbyta_w_czasie_przestoju_nie_jest_odtwarzana(self):
        from core.managers.timer_manager import recovery_timers_for_game
        self._start_p1('running', 65000, age_s=5)
        self._penalty('away', limit_ms=120000, start_offset_ms=-60000)         # odbyte 130 s > 120 s
        self.assertEqual(recovery_timers_for_game(now=self.now)['penalties']['away'], [])

    def test_okres_nierozpoczety_nie_ma_szacunku_ani_kar(self):
        from core.managers.timer_manager import recovery_timers_for_game
        r = recovery_timers_for_game(now=self.now)
        self.assertNotIn('recovery_elapsed', r['main'] or {})
        self.assertEqual(r['penalties'], {'home': [], 'away': []})

    def test_dane_panelu_bez_zmian(self):
        from core.managers.timer_manager import current_timers_for_game
        self._start_p1('running', 65000, age_s=5)
        self._penalty('home', 120000, 30000)
        c = current_timers_for_game()
        self.assertNotIn('recovery_elapsed', c['main'])
        self.assertEqual(c['penalties'], {'home': [], 'away': []})

    def test_api_settings_zawiera_dane_do_odtwarzania(self):
        self._start_p1('running', 65000, age_s=0)
        d = self.client.get('/api/settings').get_json()
        self.assertIn('recovery_timers', d)
        self.assertIn('recovery_elapsed', d['recovery_timers']['main'])
        self.assertNotIn('recovery_elapsed', d['current_timers']['main'])

    # -- zdarzenia z przegladarki
    def test_awaryjne_tworzenie_zegara_zapisuje_ostrzezenie_z_powodem(self):
        from core.extensions import socketio
        client = socketio.test_client(APP)
        with self.assertLogs(APP.logger, level='WARNING') as cap:
            client.emit('timer_plugin_create_timer', {
                'timer_id': 'x p:1', 'timer_type': 'independent', 'initial_time': 0, 'limit': 1200000,
                'recovery': True, 'recovery_expected': True, 'recovery_reason': 'corrupt', 'recovery_elapsed': 70000})
        text = "\n".join(cap.output)
        self.assertIn('AWARYJNE ODTWARZANIE ZEGARA', text)
        self.assertIn('okres trwa', text)
        self.assertIn('x p:1', text)
        self.assertIn('corrupt', text)

    def test_zwykle_tworzenie_zegara_nie_ostrzega(self):
        from core.extensions import socketio
        client = socketio.test_client(APP)
        with self.assertLogs(APP.logger, level='INFO') as cap:
            client.emit('timer_plugin_create_timer', {'timer_id': 'y p:1', 'timer_type': 'independent'})
        self.assertNotIn('AWARYJNE', "\n".join(cap.output))

    def test_ustawienie_upływu_odtworzonego_zegara_idzie_do_pluginu(self):
        from core.extensions import socketio
        client = socketio.test_client(APP)
        client.emit('timer_plugin_set_elapsed_time', {'timer_id': 'x p:1', 'elapsed_time': 70000})
        self.cm._hub_client.send_to_plugin.assert_any_call('timer-plugin', 'set_elapsed_time',
                                                           {'timer_id': 'x p:1', 'elapsed_time': 70000})
        self.cm._hub_client.send_to_plugin.reset_mock()
        client.emit('timer_plugin_set_elapsed_time', {'timer_id': 'x p:1', 'elapsed_time': -5})
        self.cm._hub_client.send_to_plugin.assert_not_called()

    def test_zalozenie_zegara_dla_nietrwajacego_okresu_nie_jest_alarmem(self):
        """Falszywy alarm z proby E2a: zwykle zalozenie zegara okresu, ktory nie trwa, nie moze byc ostrzezeniem."""
        from core.extensions import socketio
        client = socketio.test_client(APP)
        with self.assertNoLogs(APP.logger, level='WARNING'):
            client.emit('timer_plugin_create_timer', {
                'timer_id': 'x p:1', 'timer_type': 'independent', 'initial_time': 0, 'limit': 1200000,
                'recovery': True, 'recovery_expected': False, 'recovery_reason': 'none', 'recovery_elapsed': 0})

    def test_dane_odtwarzania_oznaczaja_kiedy_zegar_powinien_istniec(self):
        from core.managers.timer_manager import recovery_timers_for_game
        self.assertFalse(recovery_timers_for_game(now=self.now)['main']['recovery_expected'])    # okres nierozpoczety
        self._start_p1('running', 65000, age_s=1)
        r = recovery_timers_for_game(now=self.now)
        self.assertTrue(r['main']['recovery_expected'])                                           # okres trwa
        self._penalty('home', 120000, 30000)
        self.assertTrue(recovery_timers_for_game(now=self.now)['penalties']['home'][0]['recovery_expected'])

    def test_okres_w_pauzie_tez_wymaga_zegara_w_pluginie(self):
        from core.managers.timer_manager import recovery_timers_for_game
        self._start_p1('paused', 65000, age_s=30)
        self.assertTrue(recovery_timers_for_game(now=self.now)['main']['recovery_expected'])

    def test_okres_zakonczony_nie_wymaga_zegara_w_pluginie(self):
        from core.managers.timer_manager import recovery_timers_for_game
        gt = self._start_p1('paused', 65000, age_s=30)
        self.p1.status = self.p1.STATUS_FINISHED
        from core.extensions import db
        db.session.commit()
        self.assertFalse(recovery_timers_for_game(now=self.now)['main']['recovery_expected'])

    # -- nieszkodliwe wyscigi i odpowiedzi, ktore byly logowane jako blad/ostrzezenie
    def test_zapis_stanu_zegara_usuwanego_rownolegle_nie_jest_bledem(self):
        """Proba E2a: usuniecie kary kasuje rekord, a plugin tuz przed usunieciem wysyla ostatnie timer_updated (stopped)."""
        from unittest.mock import patch
        from sqlalchemy.orm.exc import StaleDataError
        from core.extensions import db
        self._start_p1('running', 65000, age_s=1)
        self._penalty('home', 120000, 30000, suffix='9')
        with patch.object(db.session, 'commit', side_effect=StaleDataError('UPDATE statement ... 0 were matched')):
            with self.assertNoLogs(APP.logger, level='ERROR'):
                self.tm._sync_db_timer('penalty_home_9', 5000, 'stopped')
        db.session.rollback()
        from app.models import GameTimer
        self.assertEqual(GameTimer.query.filter_by(plugin_timer_id='penalty_home_9').count(), 1)   # sesja nadal uzywalna

    def test_inny_blad_zapisu_stanu_zegara_nadal_jest_bledem(self):
        from unittest.mock import patch
        from core.extensions import db
        self._start_p1('running', 65000, age_s=1)
        with patch.object(db.session, 'commit', side_effect=RuntimeError('inny blad')):
            with self.assertLogs(APP.logger, level='ERROR'):
                self.tm._sync_db_timer(self.p1.main_timer_name, 5000, 'running')
        db.session.rollback()

    def test_odpowiedz_obs_na_zapytanie_o_stan_kamer_nie_jest_ostrzezeniem(self):
        """Proba E2a: panel rozsyla recording_command (GetRecordStatus), odpowiada tez obs-ws-plugin; moduł nie ma co z tym robic."""
        from core.managers.obs_ws_manager import ObsWsManager
        mgr = ObsWsManager(MagicMock())
        msg = {'payload': {'requestID': 'rec-status-2026-10-08 03:19:18.977412', 'requestType': 'GetRecordStatus',
                           'responseData': {'outputActive': False}}}
        with self.assertNoLogs(APP.logger, level='WARNING'):
            mgr.on_obs_response(msg)
        with self.assertLogs(APP.logger, level='WARNING'):                  # nieznane identyfikatory nadal ostrzegaja
            mgr.on_obs_response({'payload': {'requestID': 'cos-nieznanego', 'responseData': {}}})

    # -- odpowiedzi pluginu
    def test_odpowiedz_all_timers_niesie_powod_stanu_pluginu(self):
        sent = []
        self.tm._emit_to_ui = lambda name, data: sent.append((name, data))
        self.tm.on_all_timers({'payload': {'timers': [], 'count': 0, 'state_status': 'stale', 'restored_count': 0}})
        name, data = sent[0]
        self.assertEqual(name, 'timer_plugin_all_timers')
        self.assertEqual((data['state_status'], data['restored_count']), ('stale', 0))

    def test_potwierdzenie_istniejacej_kary_nie_dubluje_rekordu(self):
        from app.models import GameTimer
        self._start_p1('running', 65000, age_s=1)
        gt = self._penalty('home', 120000, 30000, suffix='7')
        self.tm._emit_to_ui = lambda *a, **k: None
        self.tm._handle_penalty_timer_created('penalty_home_7', 80000, 'running', {})
        self.assertEqual(GameTimer.query.filter_by(plugin_timer_id='penalty_home_7').count(), 1)
        self.assertEqual(GameTimer.query.get(gt.id).start_offset_ms, 30000)     # zachowany punkt odniesienia kary


if __name__ == "__main__":
    unittest.main()
