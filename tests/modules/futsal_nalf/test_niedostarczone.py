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


if __name__ == "__main__":
    unittest.main()
