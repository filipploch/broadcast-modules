"""Reguła minuty zdarzenia (krok B2): ładunki wysyłane do nakładki zawierają początek okresu (period_start_s) obok końca (period_limit_s), a nakładka
z tymi danymi pokazuje minutę zgodnie z regułą (docs/regula-minuty.md). Wspólne dla obu modułów; każdy moduł woła make(APP, 'futsal_nalf'|'garbarnia').
Nakładka to PRAWDZIWY kod hub/overlays/<nakladka>/js uruchamiany w Node (tests/modules/js/overlay_time.js)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import harness

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / 'tests' / 'modules' / 'js' / 'overlay_time.js'
NAKLADKA = {'futsal_nalf': 'futsal-nalf', 'garbarnia': 'garbarnia'}
DLUGOSC_MS = {'futsal_nalf': 1200000, 'garbarnia': 2700000}          # połowa: 20 min w NALF, 45 min w Garbarni


def uruchom_js(*args):
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Brak Node.js w PATH: testy minuty uruchamiają prawdziwy kod nakładek')
    r = subprocess.run([node, str(RUNNER), *map(str, args)], capture_output=True, text=True, encoding='utf-8', timeout=30)
    if r.returncode:
        raise RuntimeError(f'Skrypt JS zakończył się błędem:\n{r.stderr}')
    return json.loads(r.stdout)


def make(APP, modul):
    L = DLUGOSC_MS[modul]
    nakladka = NAKLADKA[modul]

    class LadunkiMinuty(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            import core.managers as cm
            from core.extensions import db
            from core.managers.period_manager import PeriodManager
            from app.models import Event, Period
            self.cm, self.db = cm, db
            cm._hub_client = MagicMock()
            tm = MagicMock()
            tm.timers = {}
            cm._timer_manager = tm
            self.pm = PeriodManager()
            self.pm.create_default_periods(game_id=self.ids['g1'])
            self.p1, self.p2 = Period.query.filter_by(game_id=self.ids['g1']).order_by(Period.period_order).all()[:2]
            self.p1.initial_time, self.p1.limit = 0, L
            self.p2.initial_time, self.p2.limit = L, L
            ev = Event(name='Bramka', short_name='BRA', image_path='static/images/x.png')
            db.session.add(ev)
            db.session.commit()
            self.event_id = ev.id
            import core.managers.session_manager as sm
            sm.activate_game(self.ids['g1'])

        def tearDown(self):
            self.cm._hub_client = None
            self.cm._timer_manager = None
            self.db.session.remove()
            self.ctx.pop()

        def _pokaz_zdarzenie(self, okres, game_time_s):
            """Wyświetlenie zdarzenia na nakładce (przycisk w panelu): zwraca ładunek show_info wysłany do stream-overlay."""
            from app.models import GameEvent
            from core.extensions import socketio
            ge = GameEvent(game_id=self.ids['g1'], event_id=self.event_id, period_id=okres.id, game_time=game_time_s, team_id=self.ids['teams'][0])
            self.db.session.add(ge)
            self.db.session.commit()
            c = socketio.test_client(APP)
            self.cm._hub_client.reset_mock()
            c.emit('toggle_game_event_info', {'game_event_id': ge.id})
            wywolania = [x for x in self.cm._hub_client.send_to_plugin.call_args_list if x.args[1] == 'show_info']
            self.assertEqual(len(wywolania), 1)
            return wywolania[0].args[2]

        def test_ladunek_zdarzenia_ma_poczatek_i_koniec_okresu_dla_obu_polowek(self):
            p1 = self._pokaz_zdarzenie(self.p1, 300)
            self.assertEqual((p1['period_start_s'], p1['period_limit_s']), (0, L // 1000))
            p2 = self._pokaz_zdarzenie(self.p2, L // 1000 + 300)
            self.assertEqual((p2['period_start_s'], p2['period_limit_s']), (L // 1000, 2 * L // 1000))

        def test_zdarzenie_w_pierwszej_sekundzie_okresu_pokazuje_pierwsza_minute(self):
            # game_time = czas gry w sekundach = początek okresu + upłynęło (dla 1. sekundy upłynęło = 0)
            p1 = self._pokaz_zdarzenie(self.p1, 0)
            self.assertEqual(uruchom_js(nakladka, 'format', p1['game_time'], p1['period_limit_s'], p1['period_start_s']), "1'")
            p2 = self._pokaz_zdarzenie(self.p2, L // 1000)
            oczekiwane = f"{L // 60000 + 1}'"                                    # 46' w Garbarni, 21' w NALF
            self.assertEqual(uruchom_js(nakladka, 'format', p2['game_time'], p2['period_limit_s'], p2['period_start_s']), oczekiwane)

        def test_zdarzenie_w_srodku_i_na_koncu_polowki_z_ladunku(self):
            polowa_min = L // 60000
            srodek = self._pokaz_zdarzenie(self.p1, 90)
            self.assertEqual(uruchom_js(nakladka, 'format', srodek['game_time'], srodek['period_limit_s'], srodek['period_start_s']), "2'")
            koniec = self._pokaz_zdarzenie(self.p1, L // 1000)
            self.assertEqual(uruchom_js(nakladka, 'format', koniec['game_time'], koniec['period_limit_s'], koniec['period_start_s']), f"{polowa_min}'")

        def test_stary_ladunek_bez_poczatku_okresu_daje_wynik_jak_dotad_bez_bledu(self):
            p2 = self._pokaz_zdarzenie(self.p2, L // 1000)
            self.assertEqual(uruchom_js(nakladka, 'format', p2['game_time'], p2['period_limit_s']), f"{L // 60000}'")      # jak przed regułą

    return LadunkiMinuty


def make_node():
    """Tabela przypadków reguły minuty (tests/modules/js/minuta_test.js) wykonana na prawdziwym kodzie obu nakładek i panelu: wchodzi do zestawu modułu."""
    class RegulaMinutyNode(unittest.TestCase):
        def test_tabela_przypadkow_zdarzenie_zmiana_panel_i_zgodnosc_wstecz(self):
            node = shutil.which('node')
            if node is None:
                raise RuntimeError('Brak Node.js w PATH')
            r = subprocess.run([node, str(REPO / 'tests' / 'modules' / 'js' / 'minuta_test.js')], capture_output=True, text=True, encoding='utf-8', timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('OK 34 przypadków', r.stdout)

    return RegulaMinutyNode
