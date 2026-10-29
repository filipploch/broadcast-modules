"""W7e-2b: funkcja awaryjna „Dodaj spoza kadry”. Lista zawodników z bazy modułu (kolejność, oznaczenia, szukanie, tryb „tylko bez drużyny”),
zawodnik już w drugiej drużynie meczu (oznaczony, bez blokady), znacznik „spoza kadry” w składzie, brak blokad powtórzonych numerów.
Wspólne dla obu modułów; każdy moduł woła make(APP, 'futsal_nalf'|'garbarnia')."""
import shutil
import subprocess
import unittest
from pathlib import Path

import harness


def make(APP, modul):
    garbarnia = modul == 'garbarnia'

    class SpozaKadry(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            from core.extensions import db
            from app.models import Player
            self.db = db
            self.A, self.B, self.C = self.ids['teams']
            self.g1 = self.ids['g1']                      # Alfa (gospodarz) – Beta
            import core.managers.session_manager as sm
            sm.activate_game(self.g1)
            self.p = {}
            dane = [('A1', 'Adamski', 'Adam', self.A, 10), ('A2', 'Zalewski', 'Zbyszek', self.A, 11),
                    ('B1', 'Bielecki', 'Bartek', self.B, 10), ('B2', 'Cichy', 'Czesław', self.B, 12),
                    ('C1', 'Dudek', 'Daniel', self.C, 7), ('X1', 'Wolny', 'Wojtek', None, 5), ('X2', 'Alfabetyczny', 'Andrzej', None, None)]
            for key, last, first, team, nr in dane:
                pl = Player(first_name=first, last_name=last, team_id=team, number=nr)
                db.session.add(pl)
                db.session.flush()
                self.p[key] = pl.id
            if garbarnia:
                from app.models.scraper import Scraper
                db.session.add(Scraper(name='laczynaspilka', folder='laczynaspilka'))
            db.session.commit()
            self.client = APP.test_client()

        def tearDown(self):
            self.db.session.remove()
            self.ctx.pop()

        def _zapisz(self, content_type, ids):
            if garbarnia:
                body = {'starters': [{'player_id': i} for i in ids[:1]], 'substitutes': [{'player_id': i} for i in ids[1:]]}
            else:
                body = {'assigned': [{'player_id': i} for i in ids]}
            r = self.client.post(f'/api/assign/{content_type}/save', json=body)
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            return r.get_json()

        def _spoza(self, content_type='home-squad', **params):
            r = self.client.get(f'/api/assign/{content_type}/outside', query_string=params)
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            return r.get_json()['players']

        def _wiersze_skladu(self, content_type='home-squad'):
            dane = self.client.get(f'/api/assign/{content_type}/data').get_json()
            return dane['starters'] + dane['substitutes'] if garbarnia else dane['assigned']

        def test_lista_ma_kolejnosc_wlasna_druzyna_potem_bez_druzyny_potem_reszta_alfabetycznie(self):
            ids = [w['player_id'] for w in self._spoza()]
            oczekiwane = [self.p[k] for k in ('A1', 'A2', 'X2', 'X1', 'B1', 'B2', 'C1')]
            # własna drużyna (Adamski, Zalewski), bez drużyny (Alfabetyczny, Wolny), reszta (Bielecki, Cichy, Dudek)
            self.assertEqual(ids, oczekiwane)

        def test_zawodnik_z_innej_druzyny_ma_napis_a_wlasny_i_wolny_nie(self):
            w = {x['player_id']: x for x in self._spoza()}
            self.assertEqual(w[self.p['B1']]['tag'], 'inna drużyna')                   # klub nieznany do W7e-2c: wiemy tylko, że drużyna inna
            self.assertEqual(w[self.p['B1']]['team_name'], 'Beta')
            self.assertEqual(w[self.p['A1']]['tag'], '')
            self.assertEqual(w[self.p['X1']]['tag'], '')
            self.assertIsNone(w[self.p['X1']]['team_name'])

        def test_tryb_tylko_bez_druzyny_i_szukanie(self):
            wolni = self._spoza(only_free='1')
            self.assertEqual({x['player_id'] for x in wolni}, {self.p['X1'], self.p['X2']})
            szukaj = self._spoza(q='biel')
            self.assertEqual([x['player_id'] for x in szukaj], [self.p['B1']])
            self.assertEqual([x['player_id'] for x in self._spoza(q='beta', only_free='1')], [])

        def test_zawodnik_w_skladzie_nie_jest_na_liscie(self):
            self._zapisz('home-squad', [self.p['A1']])
            ids = [x['player_id'] for x in self._spoza()]
            self.assertNotIn(self.p['A1'], ids)
            self.assertIn(self.p['A2'], ids)

        def test_zawodnik_z_drugiej_druzyny_meczu_jest_oznaczony_ale_mozna_go_dodac(self):
            self._zapisz('away-squad', [self.p['B1']])                                 # B1 gra w składzie gości
            w = {x['player_id']: x for x in self._spoza('home-squad')}
            self.assertTrue(w[self.p['B1']]['w_drugiej_druzynie'])
            self.assertFalse(w[self.p['B2']]['w_drugiej_druzynie'])
            self._zapisz('home-squad', [self.p['A1'], self.p['B1']])                    # dodanie po potwierdzeniu: brak blokady, zawodnik przechodzi do tego składu
            self.assertIn(self.p['B1'], [r['player_id'] for r in self._wiersze_skladu('home-squad')])
            self.assertNotIn(self.p['B1'], [r['player_id'] for r in self._wiersze_skladu('away-squad')])      # w meczu może być tylko w jednym składzie

        # -- przeniesienie z drugiego składu jest odrzucone, gdy zawodnik ma w tym meczu zdarzenia, zmiany albo kary
        KOMUNIKAT = "Zawodnik ma w tym meczu zdarzenia, nie można go przenieść do drugiego składu"

        def _zdarzenie(self, player_key):
            from app.models import Event, GameEvent, Period
            from core.managers.period_manager import PeriodManager
            if Period.query.filter_by(game_id=self.g1).count() == 0:
                PeriodManager().create_default_periods(game_id=self.g1)
            okres = Period.query.filter_by(game_id=self.g1).order_by(Period.period_order).first()
            ev = Event.query.first()
            if ev is None:
                ev = Event(name='Bramka', short_name='BRA', image_path='static/images/x.png')
                self.db.session.add(ev)
                self.db.session.flush()
            self.db.session.add(GameEvent(game_id=self.g1, event_id=ev.id, period_id=okres.id, team_id=self.B, player_id=self.p[player_key], game_time=60))
            self.db.session.commit()

        def _sprawdz_odrzucone(self):
            gosc, gospodarz = self._wiersze_skladu('away-squad'), self._wiersze_skladu('home-squad')
            body = ({'starters': [{'player_id': self.p['A1']}], 'substitutes': [{'player_id': self.p['B1']}]} if garbarnia
                    else {'assigned': [{'player_id': self.p['A1']}, {'player_id': self.p['B1']}]})
            r = self.client.post('/api/assign/home-squad/save', json=body)
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.get_json()['error'], self.KOMUNIKAT)
            # nic się nie zmieniło: B1 nadal w składzie gości, skład gospodarzy bez zmian
            self.assertEqual([x['player_id'] for x in self._wiersze_skladu('away-squad')], [x['player_id'] for x in gosc])
            self.assertEqual([x['player_id'] for x in self._wiersze_skladu('home-squad')], [x['player_id'] for x in gospodarz])
            self.assertIn(self.p['B1'], [x['player_id'] for x in self._wiersze_skladu('away-squad')])

        def test_przeniesienie_zawodnika_ze_zdarzeniami_w_meczu_jest_odrzucone(self):
            self._zapisz('away-squad', [self.p['B1']])
            self._zapisz('home-squad', [self.p['A1'], self.p['A2']])
            self._zdarzenie('B1')
            self._sprawdz_odrzucone()

        def test_zawodnik_bez_zdarzen_jest_przenoszony_a_zdarzenia_innego_zawodnika_nie_przeszkadzaja(self):
            self._zapisz('away-squad', [self.p['B1'], self.p['B2']])
            self._zdarzenie('B2')                                                          # zdarzenia ma B2, przenosimy B1
            self._zapisz('home-squad', [self.p['A1'], self.p['B1']])
            self.assertIn(self.p['B1'], [x['player_id'] for x in self._wiersze_skladu('home-squad')])
            self.assertNotIn(self.p['B1'], [x['player_id'] for x in self._wiersze_skladu('away-squad')])

        def test_zawodnik_ze_zdarzeniami_zostaje_na_swoim_skladzie_przy_zwyklym_zapisie(self):
            # odrzucenie dotyczy tylko PRZENIESIENIA z drugiego składu: zapis składu, w którym zawodnik już jest, działa jak dotąd
            self._zapisz('away-squad', [self.p['B1'], self.p['B2']])
            self._zdarzenie('B1')
            self._zapisz('away-squad', [self.p['B1'], self.p['B2']])
            self.assertEqual({x['player_id'] for x in self._wiersze_skladu('away-squad')}, {self.p['B1'], self.p['B2']})

        def test_kara_w_meczu_blokuje_przeniesienie(self):
            from core.models.base_game_timer import get_game_timer_model
            GameTimer = get_game_timer_model()
            self._zapisz('away-squad', [self.p['B1']])
            self.db.session.add(GameTimer(game_id=self.g1, timer_type='penalty', team='away', state='running', player_id=self.p['B1']))
            self.db.session.commit()
            self._sprawdz_odrzucone()

        if garbarnia:
            def test_zmiana_w_meczu_blokuje_przeniesienie_gdy_zawodnik_wchodzi_albo_schodzi(self):
                from app.models import Period
                from app.models.substitution import Substitution
                from core.managers.period_manager import PeriodManager
                for klucz_in, klucz_out in (('B1', 'B2'), ('B2', 'B1')):
                    self.db.session.rollback()
                    self._zapisz('away-squad', [self.p['B1'], self.p['B2']])
                    if Period.query.filter_by(game_id=self.g1).count() == 0:
                        PeriodManager().create_default_periods(game_id=self.g1)
                    okres = Period.query.filter_by(game_id=self.g1).first()
                    self.db.session.add(Substitution(substitution_group=1, game_time_ms=60000, game_id=self.g1, period_id=okres.id, team_id=self.B,
                                                     player_in_id=self.p[klucz_in], player_out_id=self.p[klucz_out]))
                    self.db.session.commit()
                    self._sprawdz_odrzucone()
                    Substitution.query.delete()
                    self.db.session.commit()

        def test_znacznik_spoza_kadry_tylko_dla_dodanych_awaryjnie(self):
            self._zapisz('home-squad', [self.p['A1'], self.p['B1'], self.p['X1']])
            znaczniki = {r['player_id']: r['spoza_kadry'] for r in self._wiersze_skladu()}
            self.assertEqual(znaczniki, {self.p['A1']: False, self.p['B1']: True, self.p['X1']: True})

        def test_zawodnik_bez_druzyny_w_skladzie_ma_druzyne_skladu_i_numer_z_karty(self):
            from app.models.game_player import GamePlayer
            self._zapisz('home-squad', [self.p['A1'], self.p['X1']])
            gp = GamePlayer.query.filter_by(game_id=self.g1, player_id=self.p['X1']).one()
            self.assertEqual((gp.team_id, gp.number), (self.A, 5))
            from app.models import Player
            self.assertIsNone(self.db.session.get(Player, self.p['X1']).team_id)       # karta bez zmian (nadal bez drużyny)

        def test_powtorzony_numer_nie_blokuje_dodania_spoza_kadry(self):
            odp = self._zapisz('home-squad', [self.p['A1'], self.p['B1']])             # obaj mają numer 10
            self.assertEqual(len(odp['warnings']), 1)                                   # tylko informacja
            self.assertEqual({r['player_id'] for r in self._wiersze_skladu()}, {self.p['A1'], self.p['B1']})

        def test_lista_nie_tworzy_ani_nie_zmienia_zawodnikow(self):
            from app.models import Player
            przed = [(p.id, p.first_name, p.last_name, p.team_id, p.number) for p in Player.query.order_by(Player.id)]
            self._spoza()
            self._spoza(only_free='1', q='x')
            po = [(p.id, p.first_name, p.last_name, p.team_id, p.number) for p in Player.query.order_by(Player.id)]
            self.assertEqual(przed, po)

        def test_lista_tylko_dla_skladow(self):
            r = self.client.get('/api/assign/referees/outside')
            self.assertEqual(r.status_code, 400)

    return SpozaKadry


def make_node():
    """Panel „Dodaj spoza kadry” (prawdziwy kod game-setup.js w Node, tests/modules/js/spoza_kadry_ui_test.js): wchodzi do zestawu modułu."""
    class SpozaKadryPanelNode(unittest.TestCase):
        def test_panel_dodaj_spoza_kadry_w_node(self):
            node = shutil.which('node')
            if node is None:
                raise RuntimeError('Brak Node.js w PATH')
            skrypt = Path(__file__).resolve().parent / 'js' / 'spoza_kadry_ui_test.js'
            r = subprocess.run([node, str(skrypt)], capture_output=True, text=True, encoding='utf-8', timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('OK 6 przypadków', r.stdout)

    return SpozaKadryPanelNode
