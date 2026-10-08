"""E2c: kiedy brak pluginu daje pasek w panelu i czy nakladka po starcie OBS dostaje pelny biezacy stan.

Wspolne dla obu modulow; kazdy modul ma wlasny plik test_pasek_pluginow.py, ktory wola make(APP)."""
import json
import unittest
from unittest.mock import MagicMock

import harness


def make(APP):
    class PasekPluginow(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.managers.hub_client import HubClient
            from core.managers.plugin_manager import PluginManager
            self.cm = cm
            self.hub = HubClient("ws://test", app=APP)
            self.hub.connected = True
            self.hub.ws = MagicMock()
            self.hub.module_id = "main-module"
            self.hub.required_plugins = ['timer-plugin', 'recorder-plugin', 'obs-ws-plugin']
            self.pm = PluginManager(self.hub)
            self.emitted = []
            self.pm._emit_to_ui = lambda t, d: self.emitted.append((t, d))
            self._saved = (cm._hub_client, cm._plugin_manager, cm._timer_manager)
            cm._hub_client, cm._plugin_manager = self.hub, self.pm

        def tearDown(self):
            from core.extensions import db
            self.cm._hub_client, self.cm._plugin_manager, self.cm._timer_manager = self._saved
            db.session.remove()
            self.ctx.pop()

        def _health(self, active):
            self.hub._handle_message({'type': 'health_status', 'from': 'hub', 'payload': {
                'connected_plugins': {p: {'is_active': True} for p in active}, 'plugin_health': {}}})

        def _status(self, plugin_id, status):
            self.hub._handle_message({'type': 'plugin_status', 'from': 'hub', 'payload': {'plugin_id': plugin_id, 'status': status}})

        def _obs(self, status):
            self.hub._handle_message({'type': 'obs_status', 'from': 'obs-ws-plugin', 'payload': {'status': status}})

        def _banners(self):
            return [d for t, d in self.emitted if t == 'plugin_unreachable']

        def _sent(self):
            return [json.loads(c.args[0]) for c in self.hub.ws.send.call_args_list]

        # -- plugin, ktory nie odpowiada od startu: tylko ikona
        def test_plugin_ktory_nie_odpowiada_od_startu_nie_daje_paska_nawet_przy_automatycznym_odpytywaniu(self):
            self._health(['timer-plugin'])                       # recorder nigdy sie nie pojawil
            for _ in range(3):
                self.assertFalse(self.hub.send_to_plugin('recorder-plugin', 'recording_status', {}))
            self.assertEqual(self._banners(), [])
            self.assertFalse(self.hub.plugin_online['recorder-plugin'])        # stan na ikonie: nieaktywny

        # -- plugin, ktory dzialal i przestal: pasek raz, tez przy automatycznym odpytywaniu
        def test_plugin_ktory_dzialal_i_przestal_daje_pasek_raz_takze_przy_odpytywaniu(self):
            self._health(['timer-plugin', 'recorder-plugin'])    # recorder dzialal
            self._health(['timer-plugin'])                       # i zniknal
            for _ in range(4):
                self.assertFalse(self.hub.send_to_plugin('recorder-plugin', 'recording_status', {}))
            ev = self._banners()
            self.assertEqual([e['plugin_id'] for e in ev], ['recorder-plugin'])
            self.assertEqual(ev[0]['command'], 'recording_status')

        def test_plugin_ktory_dzialal_zgloszony_przez_plugin_status_tez_daje_pasek(self):
            self._status('obs-ws-plugin', 'connected')
            self._status('obs-ws-plugin', 'disconnected')
            self.hub.send_to_plugin('obs-ws-plugin', 'obs_command', {})
            self.assertEqual([e['plugin_id'] for e in self._banners()], ['obs-ws-plugin'])

        # -- nakladka: pasek tylko gdy OBS dziala
        def test_nakladka_przy_zamknietym_obs_nie_daje_paska(self):
            self._status('stream-overlay', 'disconnected')
            self._obs('disconnected')
            self.assertFalse(self.hub.send_to_plugin('stream-overlay', 'game_data', {}))
            self.assertEqual(self._banners(), [])

        def test_nakladka_przy_dzialajacym_obs_daje_pasek_raz(self):
            self._obs('connected')
            self._status('stream-overlay', 'disconnected')
            for _ in range(3):
                self.hub.send_to_plugin('stream-overlay', 'game_data', {})
            self.assertEqual([e['plugin_id'] for e in self._banners()], ['stream-overlay'])

        def test_obs_zamkniety_po_dzialaniu_znowu_wycisza_pasek_nakladki(self):
            self._obs('connected')
            self._obs('disconnected')
            self._status('stream-overlay', 'disconnected')
            self.hub.send_to_plugin('stream-overlay', 'game_data', {})
            self.assertEqual(self._banners(), [])

        # -- nakladka po starcie OBS dostaje pelny biezacy stan
        def _mecz_z_zatrzymanym_zegarem(self):
            import core.managers.session_manager as sm
            from core.extensions import db
            from core.managers.period_manager import PeriodManager
            from core.managers.timer_manager import TimerManager
            from app.models import GameTimer, Period
            gid = self.ids['g1']
            PeriodManager().create_default_periods(game_id=gid)
            sm.activate_game(gid)
            p = Period.query.filter_by(game_id=gid).order_by(Period.period_order).first()
            db.session.add(GameTimer(game_id=gid, period_id=p.id, timer_type=GameTimer.TYPE_MAIN, plugin_timer_id=p.main_timer_name,
                                     elapsed_time_ms=90000, limit_ms=p.limit, state='paused'))
            db.session.commit()
            tm = TimerManager(self.hub)
            tm._broadcast_penalty_state = lambda *a, **k: None
            self.cm._timer_manager = tm
            return p

        def test_nakladka_prosi_o_dane_zaraz_po_starcie_obs_mimo_ze_wczesniejsze_polecenia_byly_pomijane(self):
            p = self._mecz_z_zatrzymanym_zegarem()
            # OBS byl zamkniety: nakladki nie bylo, polecenia do niej byly pomijane
            self._status('stream-overlay', 'disconnected')
            self.assertFalse(self.hub.send_to_plugin('stream-overlay', 'game_data', {}))
            self.hub.ws.send.reset_mock()

            # start OBS: nakladka sie rejestruje i prosi modul o dane (HUB nie zglasza modulowi jej polaczenia)
            self.hub._on_message(None, json.dumps({'type': 'request_game_data', 'from': 'stream-overlay', 'to': 'main-module'}))

            sent = {m['type']: m for m in self._sent() if m['to'] == 'stream-overlay'}
            self.assertIn('game_data', sent)
            for key in ('home_team_goals', 'away_team_goals', 'home_team_name', 'away_team_name'):
                self.assertIn(key, sent['game_data']['payload'])                      # wynik i druzyny (sklady w tych samych danych)
            self.assertIn('penalty_state', sent)                                       # kary
            timer = sent['timer_updated']['payload']                                   # zegar zatrzymany (bez tickow)
            self.assertEqual((timer['timer_id'], timer['elapsed_time'], timer['state']), (p.main_timer_name, 90000, 'paused'))
            self.assertEqual(self._banners(), [])

        def test_nakladka_z_biegnacym_zegarem_dostaje_dane_bez_dodatkowego_timer_updated(self):
            p = self._mecz_z_zatrzymanym_zegarem()
            from core.extensions import db
            from app.models import GameTimer
            GameTimer.query.filter_by(period_id=p.id).update({'state': 'running'})
            db.session.commit()
            self.hub._on_message(None, json.dumps({'type': 'request_game_data', 'from': 'stream-overlay', 'to': 'main-module'}))
            types = [m['type'] for m in self._sent()]
            self.assertIn('game_data', types)
            self.assertNotIn('timer_updated', types)            # biegnacy zegar sam przysyla ticki

        def test_prosba_nakladki_o_dane_bez_otwartej_sesji_nie_rzuca_wyjatku(self):
            self.hub._on_message(None, json.dumps({'type': 'request_game_data', 'from': 'stream-overlay', 'to': 'main-module'}))
            self.assertEqual([m for m in self._sent() if m['to'] == 'stream-overlay'], [])

        def test_wiadomosc_od_pluginu_oznacza_go_jako_polaczonego_i_zdejmuje_pasek(self):
            self._health(['recorder-plugin'])
            self._health([])
            self.hub.send_to_plugin('recorder-plugin', 'recording_status', {})
            self.assertEqual(len(self._banners()), 1)
            self.hub._on_message(None, json.dumps({'type': 'recorder_plugin_info', 'from': 'recorder-plugin', 'payload': {}}))
            self.assertTrue(self.hub.plugin_online['recorder-plugin'])
            self.assertEqual([d['plugin_id'] for t, d in self.emitted if t == 'plugin_reachable'], ['recorder-plugin'])

    return PasekPluginow
