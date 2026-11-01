"""W8a: wynik rzutów karnych z formularza edycji meczu (wspólne dla obu modułów): pola home/away_team_shootouts zapisują konkurs (dawniej trasa czytała inne
nazwy pól i wołała menedżera z błędnymi argumentami), a zmiana konkursu trafia do kolejki zapisu do WP z wynikiem karnych."""
import tempfile
import unittest
from pathlib import Path

import harness


def make(APP, modul):
    class EdycjaKarnych(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            from core.extensions import db
            from core.managers import wp_zapis
            from core.models.base_scraper import get_scraper_model
            from app.models import Game, Shootout
            self.db, self.wp_zapis, self.Game, self.Shootout = db, wp_zapis, Game, Shootout
            self.g1 = self.ids['g1']
            sc = get_scraper_model()(name='wp', folder='wp')
            db.session.add(sc)
            db.session.commit()
            db.session.get(Game, self.g1).set_foreign_id(sc.id, '501')
            g = db.session.get(Game, self.g1)
            g.status, g.home_team_goals, g.away_team_goals = Game.STATUS_FINISHED, 2, 2
            db.session.add(Shootout(game_id=self.g1, home_team_shootouts=0, away_team_shootouts=0))
            db.session.commit()
            self.tmp = Path(tempfile.mkdtemp(prefix='bm-karne-'))
            self.z = wp_zapis.WpZapis(APP, self.tmp / 'kolejka.db', self.tmp / 'zapis.json', lambda: None, True)
            wp_zapis.ustaw_instancje(self.z)
            wp_zapis._zainstaluj_nasluch()
            self.client = APP.test_client()

        def tearDown(self):
            self.wp_zapis.ustaw_instancje(None)
            self.db.session.remove()
            self.ctx.pop()

        def formularz(self, **pola):
            g = self.db.session.get(self.Game, self.g1)
            dane = {'status': '2', 'home_team_goals': '2', 'away_team_goals': '2', 'home_team_id': str(g.home_team_id),
                    'away_team_id': str(g.away_team_id), 'league_id': str(g.league_id)}
            dane.update(pola)
            return self.client.post(f'/games/{self.g1}/edit', data=dane)

        def konkurs(self):
            self.db.session.expire_all()
            s = self.Shootout.query.filter_by(game_id=self.g1).one()
            return s.home_team_shootouts, s.away_team_shootouts

        def test_formularz_zapisuje_wynik_karnych_z_pol_shootouts(self):
            odp = self.formularz(home_team_shootouts='4', away_team_shootouts='5')
            self.assertEqual(odp.status_code, 302)                                  # przekierowanie = zapis się udał
            self.assertEqual(self.konkurs(), (4, 5))

        def test_stare_nazwy_pol_penalties_tez_dzialaja(self):
            self.formularz(home_team_penalties='3', away_team_penalties='1')
            self.assertEqual(self.konkurs(), (3, 1))

        def test_puste_pola_nie_zmieniaja_konkursu_a_ujemne_sa_odrzucone(self):
            self.formularz(home_team_shootouts='4', away_team_shootouts='5')
            self.formularz(home_team_shootouts='', away_team_shootouts='')
            self.assertEqual(self.konkurs(), (4, 5))
            odp = self.formularz(home_team_shootouts='-1', away_team_shootouts='2')
            self.assertEqual(odp.status_code, 200)                                  # formularz wraca z komunikatem
            self.assertEqual(self.konkurs(), (4, 5))

        def test_zmiana_konkursu_z_formularza_trafia_do_kolejki_wp_z_wynikiem_karnych(self):
            self.formularz(home_team_shootouts='4', away_team_shootouts='5')
            self.assertGreaterEqual(self.z.status()['w_kolejce'], 1)
            zad = self.z._zadanie(self.g1)
            self.assertEqual((zad['state'], zad['home'], zad['away'], zad['pen_home'], zad['pen_away']), ('zakonczony', 2, 2, 4, 5))

    return EdycjaKarnych
