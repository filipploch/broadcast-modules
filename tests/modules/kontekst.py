"""E2c: kontekst (modul, sesja, mecz, okres) w poleceniach do pluginow i filtr spoznionych komunikatow.

Wspolne dla obu modulow; kazdy modul ma wlasny plik test_kontekst.py, ktory wola make(APP)."""
import json
import unittest
from unittest.mock import MagicMock

import harness


def make(APP):
    MODULE = APP.config['MODULE_NAME']

    class Kontekst(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.managers.hub_client import HubClient
            self.cm = cm
            self.hub = self._new_hub()
            self._saved = (cm._hub_client, cm._timer_manager)
            cm._hub_client = self.hub
            self.received = []
            self.hub.add_message_handler(self.received.append)

        def tearDown(self):
            from core.extensions import db
            self.cm._hub_client, self.cm._timer_manager = self._saved
            db.session.remove()
            self.ctx.pop()

        # -- pomocnicze
        def _new_hub(self):
            from core.managers.hub_client import HubClient
            hub = HubClient("ws://test", app=APP)
            hub.connected = True
            hub.ws = MagicMock()
            hub.module_id = "main-module"
            return hub

        def _sent(self):
            return [json.loads(c.args[0]) for c in self.hub.ws.send.call_args_list]

        def _open(self, game='g1'):
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            PeriodManager().create_default_periods(game_id=self.ids[game])
            sm.activate_game(self.ids[game])
            return sm.current_session_id(), self.ids[game]

        def _ctx(self, session_id, game_id, module=None, period_id=None):
            return {'module': module or MODULE, 'session_id': session_id, 'game_id': game_id, 'period_id': period_id}

        def _incoming(self, msg_type, context, sender='timer-plugin', payload=None):
            msg = {'type': msg_type, 'from': sender, 'payload': payload or {'timer_id': 't1'}}
            if context is not None:
                msg['context'] = context
            self.hub._on_message(None, json.dumps(msg))

        def _types(self):
            return [m['type'] for m in self.received]

        # -- polecenia niosa kontekst
        def test_polecenie_do_pluginu_niesie_kontekst_sesji_meczu_i_okresu(self):
            sid, gid = self._open()
            self.hub.send_to_plugin('timer-plugin', 'start_timer', {'timer_id': 't1'})
            ctx = self._sent()[-1]['context']
            self.assertEqual((ctx['module'], ctx['session_id'], ctx['game_id']), (MODULE, sid, gid))
            self.assertIsNotNone(ctx['period_id'])

        def test_polecenie_bez_sesji_ma_kontekst_z_pustymi_identyfikatorami(self):
            self.hub.send_to_plugin('timer-plugin', 'get_all_timers', {})
            ctx = self._sent()[-1]['context']
            self.assertEqual((ctx['module'], ctx['session_id'], ctx['game_id']), (MODULE, None, None))

        # -- filtr
        def test_komunikat_bez_kontekstu_przechodzi(self):
            self._open()
            self._incoming('timer_updated', None)
            self.assertEqual(self._types(), ['timer_updated'])

        def test_komunikat_ze_zgodnym_kontekstem_przechodzi_takze_dla_innego_okresu(self):
            sid, gid = self._open()
            self._incoming('timer_updated', self._ctx(sid, gid, period_id=999999))      # okres nie sluzy do odrzucania
            self.assertEqual(self._types(), ['timer_updated'])

        def test_komunikat_ze_starej_sesji_jest_odrzucony_z_powodem_w_jednym_wpisie(self):
            sid, gid = self._open()
            with self.assertLogs(APP.logger, 'WARNING') as logs:
                self._incoming('timer_started', self._ctx(sid + 5, gid))
            self.assertEqual(self.received, [])
            wpisy = [l for l in logs.output if 'Odrzucono' in l]
            self.assertEqual(len(wpisy), 1)
            self.assertIn('session_id', wpisy[0])
            self.assertIn(f'oczekiwano {sid}', wpisy[0])
            self.assertIn(f'otrzymano {sid + 5}', wpisy[0])
            self.assertEqual(self.hub.context_filter.rejected, 1)

        def test_komunikat_ze_starego_meczu_jest_odrzucony(self):
            sid, gid = self._open('g1')
            import core.managers.session_manager as sm
            zegar = [0.0]
            self.hub.context_filter._clock = lambda: zegar[0]
            sm.activate_game(self.ids['g2'])
            zegar[0] += 60.0                                     # po oknie na odpowiedzi starego meczu
            with self.assertLogs(APP.logger, 'WARNING') as logs:
                self._incoming('timer_updated', self._ctx(sid, gid))
            self.assertEqual(self.received, [])
            self.assertIn('game_id', [l for l in logs.output if 'Odrzucono' in l][0])

        def test_komunikat_z_innego_modulu_jest_odrzucony(self):
            sid, gid = self._open()
            with self.assertLogs(APP.logger, 'WARNING') as logs:
                self._incoming('timer_updated', self._ctx(sid, gid, module='inny_modul'))
            self.assertEqual(self.received, [])
            wpis = [l for l in logs.output if 'Odrzucono' in l][0]
            self.assertIn("'inny_modul'", wpis)
            self.assertIn(f"oczekiwano {MODULE!r}", wpis)

        def test_komunikaty_hub_a_nie_podlegaja_filtrowi(self):
            sid, gid = self._open()
            self._incoming('undelivered', self._ctx(sid + 1, gid + 1), sender='hub',
                           payload={'plugin_id': 'timer-plugin', 'command': 'x'})
            self.assertEqual(self._types(), ['undelivered'])

        # -- brak otwartej sesji
        def test_panel_bez_sesji_odrzuca_komunikaty_z_kontekstem_i_przepuszcza_bez_kontekstu(self):
            with self.assertLogs(APP.logger, 'WARNING') as logs:
                self._incoming('timer_updated', self._ctx(7, 42))                  # z kontekstem sesji i meczu
            self.assertEqual(self.received, [])
            self.assertEqual(len([l for l in logs.output if 'Odrzucono' in l]), 1)
            self.assertIn('oczekiwano None', logs.output[0])
            self._incoming('timer_updated', None)                                  # bez kontekstu
            self._incoming('timer_updated', self._ctx(None, None))                 # kontekst bez identyfikatorow
            self.assertEqual(self._types(), ['timer_updated', 'timer_updated'])

        # -- nastepny mecz: polecenia o meczu A przed zmiana, odpowiedzi nie sa odrzucane
        def _running_timer(self, session_id, game_id):
            from core.extensions import db
            from app.models import GameTimer, Period
            p = Period.query.filter_by(game_id=game_id).order_by(Period.period_order).first()
            gt = GameTimer(game_id=game_id, period_id=p.id, timer_type=GameTimer.TYPE_MAIN, plugin_timer_id=p.main_timer_name,
                           elapsed_time_ms=60000, limit_ms=p.limit, state='running')
            db.session.add(gt)
            db.session.commit()
            return gt

        def _wire_timer_manager(self):
            from core.managers.timer_manager import TimerManager
            tm = TimerManager(self.hub)
            tm._broadcast_penalty_state = lambda *a, **k: None
            self.cm._timer_manager = tm
            return tm

        def _record_active_game_on_send(self):
            import core.managers.session_manager as sm
            seen = []
            orig = self.hub.send

            def spy(message):
                seen.append((message.get('type'), message.get('context'), sm.current_game_id()))
                return orig(message)
            self.hub.send = spy
            return seen

        def _zmiana(self, jak):
            import core.managers.session_manager as sm
            if jak == 'next_game':
                sm.queue_game(self.ids['g2'])
                sm.next_game()
            elif jak == 'activate_game':
                sm.activate_game(self.ids['g2'])
            else:
                sm.close_session()

        def _sprawdz_zmiane_meczu(self, jak):
            sid, gid = self._open('g1')
            gt = self._running_timer(sid, gid)
            self._wire_timer_manager()
            seen = self._record_active_game_on_send()

            self._zmiana(jak)

            pauzy = [s for s in seen if s[0] == 'pause_timer']
            self.assertEqual(len(pauzy), 1, 'zmiana meczu powinna wstrzymac biegnacy zegar starego meczu')
            _, kontekst, aktywny_w_chwili_wyslania = pauzy[0]
            self.assertEqual(aktywny_w_chwili_wyslania, gid, 'polecenie o meczu A musi wyjsc, gdy A jest jeszcze biezacy')
            self.assertEqual((kontekst['session_id'], kontekst['game_id']), (sid, gid))
            self.assertEqual(self._sent()[-1]['payload'], {'timer_id': gt.plugin_timer_id})

            # odpowiedz pluginu z kontekstem meczu A dociera juz po zmianie: nie moze byc odrzucona
            self._incoming('timer_paused', self._ctx(sid, gid), payload={'timer_id': gt.plugin_timer_id})
            self.assertEqual(self._types(), ['timer_paused'])

        def test_nastepny_mecz_wstrzymuje_zegar_starego_meczu_a_odpowiedz_jest_przyjeta(self):
            self._sprawdz_zmiane_meczu('next_game')

        def test_zmiana_meczu_wstrzymuje_zegar_starego_meczu_a_odpowiedz_jest_przyjeta(self):
            self._sprawdz_zmiane_meczu('activate_game')

        def test_zamkniecie_sesji_wstrzymuje_zegar_a_odpowiedz_jest_przyjeta(self):
            self._sprawdz_zmiane_meczu('close_session')

        def test_okno_na_odpowiedzi_starego_meczu_wygasa(self):
            sid, gid = self._open('g1')
            zegar = [0.0]
            self.hub.context_filter._clock = lambda: zegar[0]
            self._running_timer(sid, gid)
            self._wire_timer_manager()
            self._zmiana('activate_game')
            zegar[0] += 60.0                                     # dlugo po zmianie meczu
            with self.assertLogs(APP.logger, 'WARNING'):
                self._incoming('timer_updated', self._ctx(sid, gid))
            self.assertEqual(self.received, [])

        def test_zmiana_meczu_bez_biegnacego_zegara_nie_wysyla_polecen(self):
            self._open('g1')
            self._wire_timer_manager()
            seen = self._record_active_game_on_send()
            self._zmiana('activate_game')
            self.assertEqual([s for s in seen if s[0] == 'pause_timer'], [])

        # -- restart modulu w trakcie meczu
        def test_restart_modulu_w_trakcie_meczu_zdarzenie_z_poprawnym_kontekstem_jest_przyjete(self):
            sid, gid = self._open('g1')
            self._running_timer(sid, gid)
            # "restart": nowy klient HUB-a (pusty filtr), stan sesji i meczu tylko w bazie
            self.hub = self._new_hub()
            self.cm._hub_client = self.hub
            self.received = []
            self.hub.add_message_handler(self.received.append)
            self._incoming('timer_updated', self._ctx(sid, gid))
            self.assertEqual(self._types(), ['timer_updated'])
            with self.assertLogs(APP.logger, 'WARNING'):
                self._incoming('timer_updated', self._ctx(sid + 1, gid))               # po restarcie dalej odrzuca cudze
            self.assertEqual(self._types(), ['timer_updated'])

        def test_stan_sesji_jest_wczytywany_z_bazy_przed_polaczeniem_z_hubem(self):
            self._open('g1')
            import inspect
            import core.managers as cm
            zrodlo = inspect.getsource(cm.initialize_core_managers)
            self.assertLess(zrodlo.index('session_manager.describe()'), zrodlo.index('HubClient(hub_url'))

    return Kontekst
