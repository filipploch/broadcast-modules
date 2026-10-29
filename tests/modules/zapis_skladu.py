"""W7e-2a: zapis składu meczowego. Drużyna w meczu to drużyna składu (nie drużyna z karty zawodnika); numer, bramkarz i opaska zawodnika z cudzej
drużyny (dodanego awaryjnie) nie zmieniają jego karty; opaska nie rusza kart zawodników innych drużyn; ostrzeżenie o powtórzonym numerze w jednym
składzie (nie blokuje zapisu). Wspólne dla obu modułów; każdy moduł woła make(APP, 'futsal_nalf'|'garbarnia')."""
import unittest

import harness


def make(APP, modul):
    garbarnia = modul == 'garbarnia'

    class ZapisSkladu(unittest.TestCase):
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
            sm.activate_game(self.g1)                     # bieżący mecz wskazuje sesja transmisji
            self.p = {}
            for team, prefix, base in ((self.A, 'A', 10), (self.B, 'B', 20)):
                for i in range(3):
                    pl = Player(first_name=f'Imie{prefix}{i}', last_name=f'Nazw{prefix}{i}', team_id=team, number=base + i)
                    db.session.add(pl)
                    db.session.flush()
                    self.p[f'{prefix}{i}'] = pl.id
            if garbarnia:                                  # lista składu Garbarni szuka scrapera „laczynaspilka” (adres drużyny)
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

        def _lista(self, content_type):
            dane = self.client.get(f'/api/assign/{content_type}/data').get_json()
            return dane, [a['player_id'] for a in (dane['starters'] + dane['substitutes'] if garbarnia else dane['assigned'])]

        def _gp(self, key):
            from app.models.game_player import GamePlayer
            self.db.session.expire_all()
            return GamePlayer.query.filter_by(game_id=self.g1, player_id=self.p[key]).one()

        def _player(self, key):
            from app.models import Player
            self.db.session.expire_all()
            return self.db.session.get(Player, self.p[key])

        def _patch(self, key, **pola):
            r = self.client.patch(f'/api/player-game/{self._gp(key).id}', json=pola)
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))

        def test_zawodnik_z_innej_druzyny_ma_w_meczu_druzyne_skladu(self):
            self._zapisz('home-squad', [self.p['A0'], self.p['B0']])
            self.assertEqual(self._gp('A0').team_id, self.A)
            self.assertEqual(self._gp('B0').team_id, self.A)                       # B0 gra w składzie gospodarza
            self.assertEqual(self._player('B0').team_id, self.B)                   # karta zawodnika bez zmian

        def test_zawodnik_z_innej_druzyny_jest_na_liscie_skladu_a_nie_na_liscie_drugiej_druzyny(self):
            self._zapisz('home-squad', [self.p['A0'], self.p['B0']])
            self.assertIn(self.p['B0'], self._lista('home-squad')[1])
            self.assertNotIn(self.p['B0'], self._lista('away-squad')[1])

        def test_zwykly_zapis_skladu_bez_zmian(self):
            self._zapisz('home-squad', [self.p['A0'], self.p['A1']])
            self.assertEqual((self._gp('A0').team_id, self._gp('A0').number), (self.A, 10))
            self.assertEqual(self._gp('A1').number, 11)

        def test_numer_zmieniony_w_meczu_przepisuje_sie_na_karte_wlasnego_zawodnika(self):
            self._zapisz('home-squad', [self.p['A0']])
            self._patch('A0', number=77)
            self.assertEqual(self._player('A0').number, 77)

        def test_numer_zawodnika_z_cudzej_druzyny_nie_zmienia_jego_karty(self):
            self._zapisz('home-squad', [self.p['A0'], self.p['B0']])
            self._patch('B0', number=99)
            self.assertEqual(self._gp('B0').number, 99)
            self.assertEqual(self._player('B0').number, 20)                        # karta w drużynie macierzystej bez zmian

        def test_numer_cudzego_zawodnika_przetrwa_ponowny_zapis_skladu(self):
            self._zapisz('home-squad', [self.p['A0'], self.p['B0']])
            self._patch('B0', number=99, is_goalkeeper=True, is_captain=True)
            self._zapisz('home-squad', [self.p['A0'], self.p['B0'], self.p['A1']])
            gp = self._gp('B0')
            self.assertEqual((gp.number, gp.is_goalkeeper, gp.is_captain, gp.team_id), (99, True, True, self.A))
            karta = self._player('B0')
            self.assertEqual((karta.number, karta.is_goalkeeper, karta.is_captain), (20, False, False))

        def test_opaska_cudzego_zawodnika_nie_rusza_kart_jego_druzyny_macierzystej(self):
            self._player('B1').is_captain = True                                    # kapitan drużyny Beta według karty
            self.db.session.commit()
            self._zapisz('home-squad', [self.p['A0'], self.p['B0']])
            self._patch('B0', is_captain=True)
            self.assertTrue(self._gp('B0').is_captain)
            self.assertFalse(self._player('B0').is_captain)                        # karta B0 bez zmian
            self.assertTrue(self._player('B1').is_captain)                         # kapitan Bety nietknięty

        def test_opaska_wlasnego_zawodnika_czysci_inne_w_skladzie_i_na_kartach_druzyny(self):
            self._zapisz('home-squad', [self.p['A0'], self.p['A1']])
            self._patch('A0', is_captain=True)
            self._patch('A1', is_captain=True)
            self.assertFalse(self._gp('A0').is_captain)
            self.assertTrue(self._gp('A1').is_captain)
            self.assertFalse(self._player('A0').is_captain)
            self.assertTrue(self._player('A1').is_captain)

        def test_powtorzony_numer_daje_ostrzezenie_ale_nie_blokuje_zapisu(self):
            odp = self._zapisz('home-squad', [self.p['A0'], self.p['A1']])
            self.assertEqual(odp['warnings'], [])
            self._patch('A1', number=10)
            dane, _ = self._lista('home-squad')
            self.assertEqual(len(dane['warnings']), 1)
            for fragment in ('10', 'NazwA0', 'NazwA1'):
                self.assertIn(fragment, dane['warnings'][0])
            odp2 = self._zapisz('home-squad', [self.p['A0'], self.p['A1']])        # zapis przechodzi
            self.assertEqual(len(odp2['warnings']), 1)

        def test_ostrzezenie_dotyczy_tylko_jednego_skladu(self):
            self._zapisz('home-squad', [self.p['A0']])                              # numer 10 u gospodarza
            self._player('B0').number = 10                                          # ten sam numer u gościa
            self.db.session.commit()
            odp = self._zapisz('away-squad', [self.p['B0']])
            self.assertEqual(odp['warnings'], [])
            self.assertEqual(self._lista('home-squad')[0]['warnings'], [])

        def test_brak_numeru_nie_jest_powtorzeniem(self):
            for k in ('A0', 'A1'):
                self._player(k).number = None
            self.db.session.commit()
            odp = self._zapisz('home-squad', [self.p['A0'], self.p['A1']])
            self.assertEqual(odp['warnings'], [])

    return ZapisSkladu
