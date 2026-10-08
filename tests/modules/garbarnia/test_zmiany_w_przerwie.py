"""E1: zmiany zawodnikow w garbarni "na zywo" — okres i czas wyznacza _resolve_live_period (substitution_manager):
  - okres trwa: ten okres, czas z panelu;
  - przerwa: NASTEPNY nierozpoczety okres, game_time_ms = jego initial_time + 1000 ms (czas z panelu pomijany);
  - mecz zakonczony: czytelny blad (wyjatek: trwa konkurs rzutow karnych -> zmiana bez okresu);
  - przed rozpoczeciem 1. okresu: bez zmian (okres 1, czas z panelu).
Regula bieznego okresu dla panelu (session_manager.select_period_for_game) pozostaje: trwajacy -> ostatnio zakonczony -> pierwszy.
"""
import json
import pathlib
import shutil
import subprocess
import unittest
from unittest.mock import MagicMock
import harness

APP, TMP = harness.boot("garbarnia")
REPO = pathlib.Path(__file__).resolve().parents[3]

HALF = 2700000          # polowa 45 min w testach (jak mecz IV ligi)
BREAK_OFFSET = 1000     # zmiana w przerwie: initial_time nastepnej czesci + 1 s


NODE_RUNNER = REPO / "tests" / "modules" / "js" / "overlay_time.js"


def _node():
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Brak Node.js w PATH: testy wzoru minuty z grafik uruchamiaja prawdziwy kod JS (tests/modules/js/overlay_time.js)")
    return node


def _run_js(*args):
    r = subprocess.run([_node(), str(NODE_RUNNER), *map(str, args)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode:
        raise RuntimeError(f"Skrypt JS zakonczyl sie bledem:\n{r.stderr}")
    return json.loads(r.stdout)


def overlay_header_time(game_time_ms, period_end_s, overlay="garbarnia"):
    """Minuta w naglowku grafiki zmiany: wykonuje PRAWDZIWE showSubstitutionOverlay z hub/overlays/<nakladka>/js/substitution.js
    (razem z utils.js) w Node i zwraca tekst przed ' ZMIANA'."""
    header = _run_js(overlay, "substitution", json.dumps(
        {"game_time_ms": game_time_ms, "period_end_s": period_end_s, "team_short_name": ""}))
    return header.split(" ZMIANA")[0]


class ZmianyNaZywo(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.ctx = APP.app_context()
        self.ctx.push()
        import core.managers as cm
        from core.extensions import db
        from core.managers.period_manager import PeriodManager
        from app.models import Player, GamePlayer, Period
        cm._hub_client = MagicMock()
        tm = MagicMock()
        tm.timers = {}
        cm._timer_manager = tm
        self.cm, self.db = cm, db
        self.pm = PeriodManager()
        self.pm.create_default_periods(game_id=self.ids['g1'])
        self.p1, self.p2 = Period.query.filter_by(game_id=self.ids['g1']).order_by(Period.period_order).all()
        self.p1.limit, self.p2.limit, self.p2.initial_time = HALF, HALF, HALF          # dwie polowy po 45 min
        db.session.commit()
        self.team = self.ids['teams'][0]
        self.players = []
        for i, role in enumerate(('starter', 'starter', 'substitute', 'substitute'), start=1):
            pl = Player(first_name=f"Gracz{i}", last_name="Test", number=i)
            db.session.add(pl)
            db.session.flush()
            db.session.add(GamePlayer(game_id=self.ids['g1'], team_id=self.team, player_id=pl.id, role=role, number=i))
            self.players.append(pl.id)
        db.session.commit()
        import core.managers.session_manager as sm
        sm.activate_game(self.ids['g1'])
        from app.managers.substitution_manager import SubstitutionManager
        self.mgr = SubstitutionManager()

    def tearDown(self):
        self.cm._hub_client = None
        self.cm._timer_manager = None
        self.db.session.remove()
        self.ctx.pop()

    def _sub(self, game_time_ms=123456, pair=(2, 0)):
        """Zmiana "na zywo": wchodzi players[pair[0]] (rezerwowy), schodzi players[pair[1]] (podstawowy)."""
        return self.mgr.make_substitution(self.ids['g1'], self.team, self.players[pair[0]], self.players[pair[1]], game_time_ms)

    # -- okres trwa
    def test_okres_trwa_zmiana_w_tym_okresie_z_czasem_z_panelu(self):
        self.pm.start_period(self.p1.id)
        s = self._sub(game_time_ms=600000)
        self.assertEqual((s.period_id, s.game_time_ms), (self.p1.id, 600000))

    # -- przerwa
    def test_przerwa_zmiana_w_nastepnym_okresie_z_jego_initial_time_plus_1s(self):
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        s = self._sub(game_time_ms=2650000)                   # czas z panelu (np. 44:10) jest w przerwie pomijany
        self.assertEqual((s.period_id, s.game_time_ms), (self.p2.id, HALF + BREAK_OFFSET))

    def test_przerwa_nie_zmienia_roli_okresu_nastepnego_ani_jego_statusu(self):
        from app.models import Period
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        self._sub()
        self.assertEqual(Period.query.get(self.p2.id).status, Period.STATUS_NOT_STARTED)

    def test_kilka_zmian_w_przerwie_to_ta_sama_minuta(self):
        from app.managers.substitution_manager import SubstitutionItem
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        subs = self.mgr.make_substitution_group(
            self.ids['g1'], self.team,
            [SubstitutionItem(self.players[2], self.players[0]), SubstitutionItem(self.players[3], self.players[1])], 777)
        self.assertEqual({(x.period_id, x.game_time_ms) for x in subs}, {(self.p2.id, HALF + BREAK_OFFSET)})

    # -- po przerwie, w drugim okresie: jak dotad
    def test_drugi_okres_trwa_czas_z_panelu(self):
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        self.pm.start_period(self.p2.id)
        s = self._sub(game_time_ms=HALF + 300000)
        self.assertEqual((s.period_id, s.game_time_ms), (self.p2.id, HALF + 300000))

    # -- mecz zakonczony
    def test_mecz_zakonczony_czytelny_blad_i_nic_nie_zapisane(self):
        from app.models import Substitution, GamePlayer
        for p in (self.p1, self.p2):
            self.pm.start_period(p.id)
            self.pm.finish_period(p.id)
        with self.assertRaises(ValueError) as cm:
            self._sub()
        self.assertIn("mecz jest zakończony", str(cm.exception))
        self.assertEqual(Substitution.query.count(), 0)
        self.assertEqual(GamePlayer.query.filter_by(player_id=self.players[2]).one().role, 'substitute')   # role bez zmian

    def test_konkurs_rzutow_karnych_zmiana_bez_okresu(self):
        from app.models import Shootout
        for p in (self.p1, self.p2):
            self.pm.start_period(p.id)
            self.pm.finish_period(p.id)
        self.db.session.add(Shootout(game_id=self.ids['g1']))
        self.db.session.commit()
        s = self._sub(game_time_ms=5)
        self.assertEqual((s.period_id, s.game_time_ms), (None, 5))

    # -- przed rozpoczeciem pierwszego okresu: BEZ ZMIAN
    def test_przed_pierwszym_okresem_dotychczasowe_zachowanie(self):
        """Opis dzisiejszego zachowania: zmiana dostaje okres 1 (jeszcze nierozpoczety, wybrany przy wyborze meczu) i czas z panelu."""
        from app.models import Period
        self.assertEqual(Period.query.get(self.p1.id).status, Period.STATUS_NOT_STARTED)
        s = self._sub(game_time_ms=0)
        self.assertEqual((s.period_id, s.game_time_ms), (self.p1.id, 0))
        s2 = self._sub(game_time_ms=90000, pair=(3, 1))
        self.assertEqual((s2.period_id, s2.game_time_ms), (self.p1.id, 90000))

    # -- jawny okres ("wstecznie") bez zmian
    def test_jawny_okres_wstecznie_bez_zmian(self):
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        s = self.mgr.make_substitution_at_time(self.ids['g1'], self.team, self.players[2], self.players[0], self.p1.id, 600)
        self.assertEqual((s.period_id, s.game_time_ms), (self.p1.id, 600000))

    # -- regula bieznego okresu dla panelu bez zmian
    def test_regula_panelu_w_przerwie_nadal_ostatnio_zakonczony(self):
        import core.managers.session_manager as sm
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        self.assertEqual(sm.current_period_id(), self.p1.id)

    # -- grafika zmiany (show_substitution)
    def _show(self, sub):
        from core.extensions import socketio
        c = socketio.test_client(APP)
        self.cm._hub_client.reset_mock()
        c.emit('show_substitution', {'period_id': sub.period_id, 'team_id': self.team, 'substitution_group': sub.substitution_group})
        calls = [x for x in self.cm._hub_client.send_to_plugin.call_args_list if x.args[1] == 'show_substitution']
        self.assertEqual(len(calls), 1)
        return calls[0].args[2]

    def test_show_substitution_w_przerwie_wysyla_czas_wewnatrz_pierwszej_minuty_nastepnej_czesci(self):
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        payload = self._show(self._sub(game_time_ms=2650000))
        self.assertEqual(payload['game_time_ms'], HALF + BREAK_OFFSET)
        self.assertEqual(payload['period_end_s'], 2 * HALF // 1000)     # koniec NASTEPNEJ czesci (do formatowania doliczonego)

    def test_grafika_pokazuje_pierwsza_minute_czesci_po_przerwie_2x45(self):
        """Wlasciciel: zmiana w przerwie = pierwsza minuta czesci po przerwie (46' przy 2x45)."""
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        payload = self._show(self._sub())
        self.assertEqual(overlay_header_time(payload['game_time_ms'], payload['period_end_s']), "46'")

    def test_grafika_pokazuje_pierwsza_minute_czesci_po_przerwie_2x40(self):
        self.p1.limit = self.p2.limit = 2400000
        self.p2.initial_time = 2400000
        self.db.session.commit()
        self.pm.start_period(self.p1.id)
        self.pm.finish_period(self.p1.id)
        payload = self._show(self._sub())
        self.assertEqual(overlay_header_time(payload['game_time_ms'], payload['period_end_s']), "41'")

    def test_znane_ograniczenie_wzoru_grafiki_na_granicy_minuty(self):
        """Do E2 (bez naprawiania): ceil(sekundy/60) na DOKLADNEJ granicy minuty daje minute o 1 mniejsza niz konwencja pilkarska
        (45:00 -> 45', a pierwsza minuta 2. polowy to 46'). Dlatego czas zmiany w przerwie to initial_time + 1 s.
        Sprawdzane na prawdziwym formatGameTimeDisplay z obu nakladek."""
        for overlay in ("garbarnia", "futsal-nalf"):
            with self.subTest(overlay=overlay):
                self.assertEqual(_run_js(overlay, "format", HALF // 1000, 2 * HALF // 1000), "45'")
                self.assertEqual(_run_js(overlay, "format", HALF // 1000 + 1, 2 * HALF // 1000), "46'")
                self.assertEqual(_run_js(overlay, "format", 2 * HALF // 1000 + 60, 2 * HALF // 1000), "90+1'")

    def test_naglowek_zmiany_w_czasie_doliczonym(self):
        self.assertEqual(overlay_header_time(2 * HALF + 61000, 2 * HALF // 1000), "90+2'")


if __name__ == "__main__":
    unittest.main()
