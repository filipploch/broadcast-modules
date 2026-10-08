"""E2b: polecenie do nieobecnego pluginu nie przepada po cichu.

HUB odsyla 'undelivered'; modul nie zostawia stanu zakladanego z gory, a panel dostaje komunikat raz na plugin.
"""
import json
import unittest
from unittest.mock import MagicMock
import harness

APP, TMP = harness.boot("futsal_nalf")


class NiedostarczonePolecenia(unittest.TestCase):
    def setUp(self):
        self.ctx = APP.app_context()
        self.ctx.push()
        import core.managers as mgrs
        from core.managers.hub_client import HubClient
        from core.managers.plugin_manager import PluginManager
        from app.managers.timer_manager import TimerManager
        self.mgrs = mgrs
        self.hub = HubClient("ws://test", app=APP)
        self.hub.connected = True
        self.hub.ws = MagicMock()
        self.hub.module_id = "futsal-nalf"
        self.hub.required_plugins = ['timer-plugin', 'obs-ws-plugin', 'recorder-plugin']
        # pluginy dzialaly od startu modulu (inaczej brak odpowiedzi nie daje paska; zob. test_pasek_pluginow)
        self.hub.plugin_seen.update(self.hub.required_plugins)
        self.emitted = []
        self.pm = PluginManager(self.hub)
        self.pm._emit_to_ui = lambda t, d: self.emitted.append((t, d))
        self.tm = TimerManager(self.hub)
        self._saved = (mgrs._plugin_manager, mgrs._timer_manager)
        mgrs._plugin_manager, mgrs._timer_manager = self.pm, self.tm

    def tearDown(self):
        self.mgrs._plugin_manager, self.mgrs._timer_manager = self._saved
        self.ctx.pop()

    def _sent(self):
        return [json.loads(c.args[0]) for c in self.hub.ws.send.call_args_list]

    def _events(self, name):
        return [d for t, d in self.emitted if t == name]

    def _undelivered(self, plugin, command, payload):
        self.hub._handle_message({'type': 'undelivered', 'from': 'hub', 'payload': {
            'plugin_id': plugin, 'command': command, 'command_payload': payload}})

    def test_znany_rozlaczony_plugin_nie_dostaje_polecenia_a_stan_zegara_sie_nie_zmienia(self):
        self.tm.timers['t1'] = {'timer_id': 't1', 'state': 'idle'}
        self.hub._handle_message({'type': 'plugin_status', 'payload': {'plugin_id': 'timer-plugin', 'status': 'disconnected'}})
        self.assertFalse(self.tm.start_timer('t1'))
        self.assertEqual(self.tm.timers['t1']['state'], 'idle')
        self.assertEqual(self._sent(), [])
        self.assertEqual(len(self._events('plugin_unreachable')), 1)
        self.assertEqual(self._events('plugin_unreachable')[0]['plugin_id'], 'timer-plugin')

    def test_plugin_o_nieznanym_stanie_dostaje_polecenie(self):
        self.tm.timers['t1'] = {'timer_id': 't1', 'state': 'idle'}
        self.assertTrue(self.tm.start_timer('t1'))
        self.assertEqual(self.tm.timers['t1']['state'], 'running')
        self.assertEqual(self._sent()[0]['to'], 'timer-plugin')

    def test_niedostarczone_cofa_stan_zakladany_z_gory(self):
        self.tm.timers['t1'] = {'timer_id': 't1', 'state': 'idle'}
        self.tm.start_timer('t1')                       # moduł jeszcze nie wiedział, że plugin padł
        self._undelivered('timer-plugin', 'start_timer', {'timer_id': 't1'})
        self.assertEqual(self.tm.timers['t1']['state'], 'idle')
        self.assertEqual(len(self._events('plugin_unreachable')), 1)
        self.assertFalse(self.hub.send_to_plugin('timer-plugin', 'start_timer', {'timer_id': 't1'}))

    def test_wznowienie_i_pauza_wracaja_do_poprzedniego_stanu(self):
        self.tm.timers['t1'] = {'timer_id': 't1', 'state': 'running'}
        self.tm.pause_timer('t1')
        self._undelivered('timer-plugin', 'pause_timer', {'timer_id': 't1'})
        self.assertEqual(self.tm.timers['t1']['state'], 'running')
        self.tm.timers['t2'] = {'timer_id': 't2', 'state': 'paused'}
        self.tm.resume_timer('t2')
        self._undelivered('timer-plugin', 'resume_timer', {'timer_id': 't2'})
        self.assertEqual(self.tm.timers['t2']['state'], 'paused')

    def test_komunikat_raz_na_plugin_mimo_wielu_polecen(self):
        for i in range(5):
            self._undelivered('obs-ws-plugin', 'obs_command', {'n': i})
        self._undelivered('recorder-plugin', 'start', {})
        ev = self._events('plugin_unreachable')
        self.assertEqual(sorted(e['plugin_id'] for e in ev), ['obs-ws-plugin', 'recorder-plugin'])

    def test_komunikat_znika_po_powrocie_pluginu(self):
        self._undelivered('timer-plugin', 'start_timer', {'timer_id': 't1'})
        self.hub._handle_message({'type': 'plugin_status', 'payload': {'plugin_id': 'timer-plugin', 'status': 'connected'}})
        self.assertEqual(self._events('plugin_reachable'), [{'plugin_id': 'timer-plugin'}])
        self.assertNotIn('timer-plugin', self.pm.unreachable)
        self.tm.timers['t1'] = {'timer_id': 't1', 'state': 'idle'}
        self.assertTrue(self.tm.start_timer('t1'))      # polecenia znów idą

    def test_raport_hub_health_status_ustawia_obecnosc_i_flage_w_panelu(self):
        health = {'type': 'health_status', 'payload': {
            'connected_plugins': {'obs-ws-plugin': {'is_active': True}}, 'plugin_health': {}}}
        self.hub._handle_message(health)
        self.assertFalse(self.hub.plugin_online['timer-plugin'])
        self.assertTrue(self.hub.plugin_online['obs-ws-plugin'])
        self.assertFalse(self.hub.send_to_plugin('timer-plugin', 'start_timer', {'timer_id': 'x'}))
        self.hub._handle_message(health)
        states = self._events('plugins_states')[-1]
        self.assertTrue(states['timer-plugin']['unreachable'])
        self.assertFalse(states['obs-ws-plugin']['unreachable'])
        # po powrocie pluginu w raporcie flaga znika
        self.hub._handle_message({'type': 'health_status', 'payload': {
            'connected_plugins': {'timer-plugin': {'is_active': True}}, 'plugin_health': {}}})
        self.assertFalse(self._events('plugins_states')[-1]['timer-plugin']['unreachable'])

    def test_nakladka_nieobecna_nie_daje_paska_w_panelu(self):
        # nakladka (stream-overlay) nie jest pluginem wymaganym: przy zamknietym OBS jej brak jest normalny
        self.hub._handle_message({'type': 'plugin_status', 'payload': {'plugin_id': 'stream-overlay', 'status': 'disconnected'}})
        self.assertFalse(self.hub.send_to_plugin('stream-overlay', 'game_data', {}))     # polecenie pomijane
        self._undelivered('stream-overlay', 'game_data', {})                               # raport HUB-a tez
        self.assertEqual(self._events('plugin_unreachable'), [])
        self.assertNotIn('stream-overlay', self.pm.unreachable)

    def test_plugin_ktory_sie_poddal_ma_trwaly_komunikat_do_rejestracji(self):
        self.hub._handle_message({'type': 'plugin_gave_up', 'payload': {'plugin_id': 'timer-plugin'}})
        self.hub._handle_message({'type': 'plugin_gave_up', 'payload': {'plugin_id': 'timer-plugin'}})   # przypomnienie z HUB-a
        self.assertEqual(self._events('plugin_gave_up'), [{'plugin_id': 'timer-plugin'}])               # komunikat raz
        self.assertFalse(self.hub.plugin_online['timer-plugin'])
        # trwa po odswiezeniu strony: flaga w stanie pluginow wysylanym przy kazdym raporcie
        self.hub._handle_message({'type': 'health_status', 'payload': {'connected_plugins': {}, 'plugin_health': {}}})
        self.assertTrue(self._events('plugins_states')[-1]['timer-plugin']['gave_up'])
        # znika po rejestracji pluginu
        self.hub._handle_message({'type': 'plugin_status', 'payload': {'plugin_id': 'timer-plugin', 'status': 'connected'}})
        self.assertEqual(self._events('plugin_reachable'), [{'plugin_id': 'timer-plugin'}])
        self.hub._handle_message({'type': 'health_status', 'payload': {
            'connected_plugins': {'timer-plugin': {'is_active': True}}, 'plugin_health': {}}})
        self.assertFalse(self._events('plugins_states')[-1]['timer-plugin']['gave_up'])

    def test_prosba_o_restart_idzie_do_hub_a_tylko_dla_obslugiwanych_pluginow(self):
        self.assertTrue(self.hub.request_plugin_restart('timer-plugin'))
        sent = self._sent()[-1]
        self.assertEqual((sent['to'], sent['type'], sent['payload']), ('hub', 'restart_plugin', {'plugin_id': 'timer-plugin'}))
        n = len(self._sent())
        self.assertFalse(self.hub.request_plugin_restart('stream-overlay'))
        self.assertFalse(self.hub.request_plugin_restart('cokolwiek'))
        self.assertEqual(len(self._sent()), n)

    def test_restart_dziala_mimo_ze_plugin_jest_uznany_za_rozlaczony(self):
        # polecenie restartu idzie do HUB-a, nie do pluginu, wiec nie podlega odrzucaniu dla rozlaczonych
        self.hub.plugin_online['timer-plugin'] = False
        self.assertTrue(self.hub.request_plugin_restart('timer-plugin'))

    def test_wynik_restartu_trafia_do_panelu(self):
        import core.extensions as ext
        emitted = []
        orig = ext.socketio.emit
        ext.socketio.emit = lambda name, data=None, **kw: emitted.append((name, data))
        try:
            self.hub._handle_message({'type': 'plugin_restart_result', 'payload': {'plugin_id': 'timer-plugin', 'ok': False, 'error': 'x'}})
        finally:
            ext.socketio.emit = orig
        self.assertEqual(emitted, [('plugin_restart_result', {'plugin_id': 'timer-plugin', 'ok': False, 'error': 'x'})])


if __name__ == "__main__":
    unittest.main()
