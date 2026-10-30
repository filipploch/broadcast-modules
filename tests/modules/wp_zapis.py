"""W8a: zapis stanu i wyniku meczu do WP (core/managers/wp_zapis.py): nasłuch zmian, kolejka, ponawianie, wyłącznik, konflikty, pętla zwrotna, panel.
Wspólne dla obu modułów; każdy moduł woła make(APP, 'futsal_nalf'|'garbarnia'). WP to atrapa HTTP (nie prawdziwy WP; prawdziwą trasę sprawdza dry_run_w8a_wp.py)."""
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import harness


class AtrapaWp:
    """Przyjmuje POST bm/v1/event/<id>/state. tryb: ok | blad500 | konflikt | wolny."""

    def __init__(self):
        self.tryb = 'ok'
        self.zapytania = []
        self.opoznienie = 0
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get('Content-Length') or 0)
                cialo = json.loads(self.rfile.read(n).decode() or '{}')
                route = self.path.split('rest_route=')[-1]
                fake.zapytania.append((route, cialo))
                if fake.opoznienie:
                    time.sleep(fake.opoznienie)
                kod, odp = 200, {'ok': True, 'duplicate': False, 'seq': cialo.get('seq'), 'state': cialo.get('state')}
                if fake.tryb == 'blad500':
                    kod, odp = 500, {'code': 'x'}
                elif fake.tryb == 'konflikt':
                    kod, odp = 409, {'code': 'bm_wp_result', 'message': 'WP ma inny wynik tego meczu (5:0)', 'data': {'status': 409, 'wp_result': [5, 0]}}
                raw = json.dumps(odp).encode()
                self.send_response(kod)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except OSError:
                    pass                                                           # klient zerwał połączenie po limicie czasu (test wolnego WP)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def zamknij(self):
        self.server.shutdown()
        self.server.server_close()


def make(APP, modul):
    class ZapisDoWp(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.ids = harness.seed(APP)
            self.ctx = APP.app_context()
            self.ctx.push()
            from core.extensions import db
            from core.managers import wp_zapis
            from core.managers.wp_client import WpClient, WpConfig
            from app.models import Game
            from core.models.base_scraper import get_scraper_model
            self.db, self.wp_zapis, self.Game = db, wp_zapis, Game
            self.fake = AtrapaWp()
            self.tmp = Path(tempfile.mkdtemp(prefix='bm-zapis-'))
            sc = get_scraper_model()(name='wp', folder='wp')
            db.session.add(sc)
            db.session.commit()
            self.g1, self.g2 = self.ids['g1'], self.ids['g2']
            db.session.get(Game, self.g1).set_foreign_id(sc.id, '501')              # g1 powiązany z WP; g2 nie
            self.czas = [1000.0]
            cfg = WpConfig(enabled=True, url=f'http://127.0.0.1:{self.fake.port}', user='u', password='p')
            self.z = wp_zapis.WpZapis(APP, self.tmp / 'kolejka.db', self.tmp / 'zapis.json', lambda: WpClient(cfg, timeout=1), True, zegar=lambda: self.czas[0])
            wp_zapis.ustaw_instancje(self.z)
            wp_zapis._zainstaluj_nasluch()
            self.client = APP.test_client()

        def tearDown(self):
            self.wp_zapis.ustaw_instancje(None)
            self.fake.zamknij()
            self.db.session.remove()
            self.ctx.pop()

        def mecz(self, gid=None):
            self.db.session.expire_all()
            return self.db.session.get(self.Game, gid or self.g1)

        def zmien(self, **pola):
            g = self.mecz()
            for k, v in pola.items():
                setattr(g, k, v)
            self.db.session.commit()

        def wyslij(self, dt=0):
            self.czas[0] += dt
            return self.z.przetworz_raz()

        def w_kolejce(self):
            return self.z.status()['w_kolejce']

        # ---- nasłuch obejmuje miejsca zmiany wyniku/stanu
        def test_start_meczu_i_gol_trafiaja_do_kolejki_i_wysylaja_ostatni_stan(self):
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            self.zmien(home_team_goals=1)
            self.zmien(home_team_goals=2)
            self.assertEqual(self.w_kolejce(), 1)                                         # zmiany się łączą: jeden wpis na mecz
            self.assertEqual(self.wyslij(), 1)
            self.assertEqual(len(self.fake.zapytania), 1)
            route, cialo = self.fake.zapytania[0]
            self.assertTrue(route.endswith('/bm/v1/event/501/state'), route)
            self.assertEqual((cialo['state'], cialo['home'], cialo['away']), ('trwa', 2, 0))
            self.assertEqual(self.w_kolejce(), 0)

        def test_numer_zapisu_rosnie_przy_kazdej_zmianie(self):
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            self.wyslij()
            self.zmien(home_team_goals=1)
            self.wyslij()
            seqy = [c['seq'] for _, c in self.fake.zapytania]
            self.assertEqual(len(seqy), 2)
            self.assertLess(seqy[0], seqy[1])

        def test_zakonczony_mecz_wysyla_wynik_koncowy(self):
            self.zmien(status=self.Game.STATUS_FINISHED, home_team_goals=3, away_team_goals=1)
            self.wyslij()
            cialo = self.fake.zapytania[-1][1]
            self.assertEqual((cialo['state'], cialo['home'], cialo['away']), ('zakonczony', 3, 1))

        def test_nierozpoczety_nie_niesie_wyniku(self):
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=1, away_team_goals=0)
            self.wyslij()
            self.zmien(status=self.Game.STATUS_NOT_STARTED, home_team_goals=None, away_team_goals=None)
            self.wyslij()
            cialo = self.fake.zapytania[-1][1]
            self.assertEqual((cialo['state'], cialo['home'], cialo['away']), ('nierozpoczety', None, None))

        def test_wszystkie_miejsca_zmiany_zostawiaja_wpis_w_kolejce(self):
            from core.managers.game_manager import GameManager
            from core.managers.period_manager import PeriodManager
            gm = GameManager()
            pm = PeriodManager()
            pm.create_default_periods(game_id=self.g1)
            okres = self.mecz().get_periods_list()[0]
            NS, PE, FI = self.Game.STATUS_NOT_STARTED, self.Game.STATUS_PENDING, self.Game.STATUS_FINISHED

            def ustaw(status=None, h=None, a=None):
                g = self.mecz()
                g.status = NS if status is None else status
                g.home_team_goals, g.away_team_goals = h, a
                self.db.session.commit()
            # (nazwa, stan wyjściowy ustawiany bez zapisu do WP, akcja)
            akcje = [
                ('game_manager.update_game (wynik)', lambda: ustaw(PE, 0, 0), lambda: gm.update_game(self.g1, home_team_goals=2, away_team_goals=1)),
                ('game_manager.set_game_status', lambda: ustaw(NS), lambda: gm.set_game_status(self.g1, PE)),
                ('PATCH /api/games/<id>/score', lambda: ustaw(PE, 0, 0), lambda: self.client.patch(f'/api/games/{self.g1}/score', json={'home_team_goals': 4, 'away_team_goals': 4})),
                ('PATCH /api/games/<id>/status', lambda: ustaw(PE, 1, 1), lambda: self.client.patch(f'/api/games/{self.g1}/status', json={'status': 2})),
                ('POST /games/<id>/edit (formularz)', lambda: ustaw(PE, 0, 0), lambda: self.client.post(f'/games/{self.g1}/edit', data={'home_team_goals': '7', 'away_team_goals': '6'})),
                ('period_manager.increment_period_goal (gol)', lambda: ustaw(PE, 5, 5), lambda: pm.increment_period_goal(okres.id, 'home', 1)),
                ('period_manager.update_period_score', lambda: ustaw(PE, 5, 5), lambda: pm.update_period_score(okres.id, 9, 9)),
                ('POST /api/games/<id>/finish', lambda: ustaw(PE, 1, 0), lambda: self.client.post(f'/api/games/{self.g1}/finish')),
            ]
            for nazwa, przygotuj, akcja in akcje:
                with self.wp_zapis.bez_zapisu_do_wp():
                    przygotuj()
                with self.z.kolejka._polacz() as c:
                    c.execute('UPDATE mecze SET wyslano_seq = seq')                    # czysty stan „nic do wysłania”
                self.assertEqual(self.w_kolejce(), 0, nazwa)
                odp = akcja()
                self.db.session.expire_all()
                self.assertEqual(self.w_kolejce(), 1, f'{nazwa}: zmiana nie trafiła do kolejki (odpowiedź {getattr(odp, "status_code", odp)})')

        # ---- pętla zwrotna
        def test_zmiany_w_bloku_bez_zapisu_do_wp_nie_trafiaja_do_kolejki(self):
            with self.wp_zapis.bez_zapisu_do_wp():
                self.zmien(status=self.Game.STATUS_FINISHED, home_team_goals=2, away_team_goals=2)
            self.assertEqual(self.w_kolejce(), 0)
            self.zmien(home_team_goals=3)                                                 # po wyjściu z bloku znów zbieramy
            self.assertEqual(self.w_kolejce(), 1)

        def test_pobierz_z_wp_nie_wpisuje_niczego_do_kolejki(self):
            import wp_pobieranie as wpp
            from core.managers.wp_client import WpClient
            from core.managers.wp_pull import pobierz_pare
            wp = wpp.wypelnij(wpp.FakeWpPull())
            tmp = Path(tempfile.mkdtemp(prefix='bm-pull-'))
            logos = tmp / 'logos'
            (logos / 'modul').mkdir(parents=True)
            for f in ('Garbarnia.png', 'Chelmek.png', 'default.png'):
                (logos / 'modul' / f).write_bytes(b'png')
            (logos / 'default.png').write_bytes(b'png')
            try:
                klient = WpClient(wpp.make_cfg(wp.port, 'u', 'p'), timeout=3)
                wynik = pobierz_pare(klient, self.db, wpp.L, wpp.S, logos, 'modul', tmp / 'kopie-wp', True)
                self.assertTrue(wynik['ok'] and wynik['zapisano'], wynik)
                self.assertEqual(self.w_kolejce(), 0)                                      # nowe mecze i wyniki z WP nie wracają do WP
                wp.znajdz('events', 201)['main_results'] = ['0', '5']                      # organizator poprawia wynik w WP
                wynik = pobierz_pare(klient, self.db, wpp.L, wpp.S, logos, 'modul', tmp / 'kopie-wp', True)
                self.assertTrue(wynik['ok'], wynik)
                self.assertEqual(self.w_kolejce(), 0)
            finally:
                wp.close()

        # ---- awaria WP, ponawianie, limit czasu
        def test_awaria_wp_nie_wywraca_i_ponawia_z_odstepami(self):
            self.fake.tryb = 'blad500'
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            self.assertEqual(self.wyslij(), 0)
            st = self.z.status()
            self.assertEqual(st['w_kolejce'], 1)
            self.assertIn('500', st['ostatni_blad']['tekst'])
            n = len(self.fake.zapytania)
            self.wyslij(1)                                                                 # za wcześnie (odstęp 2 s)
            self.assertEqual(len(self.fake.zapytania), n)
            self.fake.tryb = 'ok'
            self.assertEqual(self.wyslij(2), 1)                                            # po odstępie wychodzi i kolejka schodzi
            self.assertEqual(self.w_kolejce(), 0)
            self.assertIsNone(self.z.status()['ostatni_blad'])

        def test_odstepy_ponawiania_rosna_do_minuty(self):
            self.fake.tryb = 'blad500'
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            odstepy = []
            for _ in range(6):
                t0 = self.czas[0]
                self.wyslij()
                with self.z.kolejka._polacz() as c:
                    odstepy.append(round(c.execute('SELECT nastepna FROM mecze').fetchone()[0] - t0))
                self.czas[0] = self.czas[0] + odstepy[-1]
            self.assertEqual(odstepy, [2, 5, 15, 60, 60, 60])

        def test_powolny_wp_nie_blokuje_dluzej_niz_limit_czasu(self):
            self.fake.opoznienie = 3
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            t = time.time()
            self.assertEqual(self.wyslij(), 0)
            self.assertLess(time.time() - t, 2.5)                                          # limit czasu klienta w teście 1 s
            self.assertEqual(self.w_kolejce(), 1)
            self.assertTrue(self.z.status()['ostatni_blad'])

        def test_zmiana_w_trakcie_awarii_wysyla_tylko_ostatni_stan(self):
            self.fake.tryb = 'blad500'
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            self.wyslij()
            self.zmien(home_team_goals=1)
            self.zmien(home_team_goals=2)
            self.fake.tryb = 'ok'
            self.fake.zapytania.clear()
            self.wyslij()
            self.assertEqual([(c['home'], c['away']) for _, c in self.fake.zapytania], [(2, 0)])

        # ---- wyłącznik
        def test_wylacznik_gromadzi_a_po_wlaczeniu_wysyla_ostatni_stan(self):
            self.z.ustaw_wlaczony(False)
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            self.zmien(home_team_goals=1)
            self.assertEqual(self.wyslij(), 0)
            self.assertEqual(self.fake.zapytania, [])
            self.assertEqual(self.w_kolejce(), 1)
            self.z.ustaw_wlaczony(True)
            self.assertEqual(self.wyslij(), 1)
            self.assertEqual((self.fake.zapytania[-1][1]['home'], self.fake.zapytania[-1][1]['away']), (1, 0))

        def test_wylacznik_przetrwa_restart_a_domyslnie_jest_wlaczony(self):
            self.assertTrue(self.z.wlaczony())
            self.z.ustaw_wlaczony(False)
            z2 = self.wp_zapis.WpZapis(APP, self.tmp / 'kolejka.db', self.tmp / 'zapis.json', self.z.klient_fabryka, True)
            self.assertFalse(z2.wlaczony())

        def test_niezaskonfigurowany_zapis_nic_nie_zbiera_ani_nie_wysyla(self):
            self.z.skonfigurowany = False
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            self.assertEqual(self.w_kolejce(), 0)
            self.assertEqual(self.wyslij(), 0)

        # ---- konflikty i pomijanie
        def test_konflikt_409_jest_widoczny_i_nie_jest_ponawiany_w_petli(self):
            self.fake.tryb = 'konflikt'
            self.zmien(status=self.Game.STATUS_FINISHED, home_team_goals=2, away_team_goals=2)
            self.assertEqual(self.wyslij(), 0)
            st = self.z.status()
            self.assertEqual(st['w_kolejce'], 0)
            self.assertEqual(len(st['odrzucone']), 1)
            self.assertIn('5:0', st['odrzucone'][0]['powod'])
            n = len(self.fake.zapytania)
            self.wyslij(120)
            self.assertEqual(len(self.fake.zapytania), n)                                  # bez ponawiania
            self.fake.tryb = 'ok'
            self.zmien(home_team_goals=5, away_team_goals=0)                               # nowa zmiana operatora: ponowna próba
            self.assertEqual(self.wyslij(), 1)
            self.assertEqual(self.z.status()['odrzucone'], [])

        def test_mecz_bez_powiazania_z_wp_jest_pomijany_bez_bledu(self):
            g = self.mecz(self.g2)
            g.status = self.Game.STATUS_PENDING
            self.db.session.commit()
            self.assertEqual(self.w_kolejce(), 1)
            self.assertEqual(self.wyslij(), 0)
            self.assertEqual(self.fake.zapytania, [])
            self.assertEqual(self.w_kolejce(), 0)
            self.assertIsNone(self.z.status()['ostatni_blad'])

        def test_zakonczony_bez_wyniku_jest_odrzucony_z_komunikatem(self):
            self.zmien(status=self.Game.STATUS_FINISHED, home_team_goals=None, away_team_goals=None)
            self.wyslij()
            self.assertEqual(self.fake.zapytania, [])
            self.assertIn('bez wyniku', self.z.status()['odrzucone'][0]['powod'])

        def test_ten_sam_stan_nie_jest_wysylany_drugi_raz(self):
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=1, away_team_goals=0)
            self.wyslij()
            self.z.zglos(self.g1)                                                          # np. ponowne zgłoszenie bez zmiany stanu
            self.wyslij()
            self.assertEqual(len(self.fake.zapytania), 1)

        def test_kolejka_przezywa_restart_modulu(self):
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            z2 = self.wp_zapis.WpZapis(APP, self.tmp / 'kolejka.db', self.tmp / 'zapis.json', self.z.klient_fabryka, True, zegar=lambda: self.czas[0])
            self.assertEqual(z2.status()['w_kolejce'], 1)
            self.assertEqual(z2.przetworz_raz(), 1)

        # ---- które bazy mogą zapisywać
        def test_baza_proba_i_testy_nie_wlaczaja_zapisu_do_wp(self):
            from core.managers.wp_client import WpConfig
            cfg = WpConfig(enabled=True, user='u', password='p')
            sk = self.wp_zapis._skonfigurowany
            app = type('A', (), {'config': {}})()
            import os
            stare = {k: os.environ.pop(k, None) for k in ('BM_WP_ZAPIS', 'BM_WP_ZAPIS_PROBA')}
            try:
                self.assertTrue(sk(app, cfg, 'database.db'))
                self.assertFalse(sk(app, cfg, 'database-proba.db'))
                self.assertFalse(sk(app, WpConfig(enabled=True), 'database.db'))                 # bez danych logowania
                self.assertFalse(sk(app, WpConfig(enabled=False, user='u', password='p'), 'database.db'))
                self.assertFalse(sk(type('A', (), {'config': {'TESTING': True}})(), cfg, 'database.db'))
                os.environ['BM_WP_ZAPIS_PROBA'] = '1'
                self.assertTrue(sk(app, cfg, 'database-proba.db'))
                os.environ['BM_WP_ZAPIS'] = '0'
                self.assertFalse(sk(app, cfg, 'database.db'))
            finally:
                for k, v in stare.items():
                    os.environ.pop(k, None)
                    if v is not None:
                        os.environ[k] = v

        # ---- panel: stan zapisu, wyłącznik, zakończenie meczu
        def test_panel_pokazuje_stan_zapisu_wylacznik_i_ponowienie(self):
            self.fake.tryb = 'blad500'
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            self.wyslij()
            s = self.client.get('/api/wp-zapis/status').get_json()
            self.assertTrue(s['skonfigurowany'] and s['wlaczony'])
            self.assertEqual(s['w_kolejce'], 1)
            self.assertIn('500', s['ostatni_blad']['tekst'])
            s = self.client.post('/api/wp-zapis/wlacznik', json={'wlaczony': False}).get_json()
            self.assertFalse(s['wlaczony'])
            self.client.post('/api/wp-zapis/wlacznik', json={'wlaczony': True})
            self.fake.tryb = 'ok'
            self.client.post('/api/wp-zapis/ponow')
            self.assertEqual(self.wyslij(), 1)
            self.assertEqual(self.client.get('/api/wp-zapis/status').get_json()['w_kolejce'], 0)

        def test_nieaktywny_zapis_podaje_powod_w_statusie_i_w_samokontroli(self):
            """Próba W8a-min nie przeszła, bo zapis był cicho nieaktywny (HUB wskazał moduł folder WP bez danych logowania): powód musi być widoczny."""
            import os
            from core.managers.wp_client import WpConfig
            pw = self.wp_zapis.powod_nieaktywnosci
            app = type('A', (), {'config': {}})()
            stare = {k: os.environ.pop(k, None) for k in ('BM_WP_ZAPIS', 'BM_WP_ZAPIS_PROBA')}
            try:
                self.assertIsNone(pw(app, WpConfig(enabled=True, user='u', password='p'), 'database.db'))
                self.assertIn('brak danych logowania', pw(app, WpConfig(enabled=True, creds_file='X:/nie-ma/dane-api-nalf.json'), 'database.db'))
                self.assertIn('dane-api-nalf.json', pw(app, WpConfig(enabled=True, creds_file='X:/nie-ma/dane-api-nalf.json'), 'database.db'))
                self.assertIn('BM_WP_ZAPIS_PROBA=1', pw(app, WpConfig(enabled=True, user='u', password='p'), 'database-proba.db'))
                self.assertIn('nie ma własnego WP', pw(app, WpConfig(enabled=False), 'database.db'))
                self.assertIn('BM_WP_ZAPIS=0', (os.environ.__setitem__('BM_WP_ZAPIS', '0'), pw(app, WpConfig(enabled=True, user='u', password='p'), 'database.db'))[1])
            finally:
                for k, v in stare.items():
                    os.environ.pop(k, None)
                    if v is not None:
                        os.environ[k] = v
            self.z.skonfigurowany, self.z.powod = False, 'baza database-proba.db nie jest bazą operacyjną'
            s = self.client.get('/api/wp-zapis/status').get_json()
            self.assertFalse(s['skonfigurowany'])
            self.assertIn('database-proba.db', s['powod'])
            self.wp_zapis.ustaw_instancje(None)                                                             # moduł bez zainicjowanego zapisu też odpowiada, z powodem
            s = self.client.get('/api/wp-zapis/status').get_json()
            self.assertFalse(s['skonfigurowany'])
            self.assertTrue(s['powod'])

        def test_aktywny_zapis_podaje_adres_i_wersje_w_statusie(self):
            self.z.adres, self.z.wersja = 'http://127.0.0.1:8099', 'etap/test, abc1234'
            s = self.client.get('/api/wp-zapis/status').get_json()
            self.assertEqual((s['adres'], s['wersja'], s['powod']), ('http://127.0.0.1:8099', 'etap/test, abc1234', ''))

        def test_panel_bez_konfiguracji_zapisu_odpowiada_i_odrzuca_zmiany(self):
            self.z.skonfigurowany = False
            s = self.client.get('/api/wp-zapis/status').get_json()
            self.assertFalse(s['skonfigurowany'])
            self.assertEqual(self.client.post('/api/wp-zapis/wlacznik', json={'wlaczony': False}).status_code, 400)

        def test_koniec_ostatniego_okresu_nie_konczy_meczu_a_przycisk_konczy(self):
            from unittest.mock import MagicMock
            import core.managers as cm
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            from app.managers.timer_manager import TimerManager
            from app.models import Period
            cm._hub_client = MagicMock()
            tm = TimerManager(cm._hub_client)
            tm._broadcast_penalty_state = lambda *a, **k: None
            cm._timer_manager = tm
            try:
                PeriodManager().create_default_periods(game_id=self.g1)
                sm.activate_game(self.g1)
                p1, p2 = Period.query.filter_by(game_id=self.g1).order_by(Period.period_order).all()[:2]
                self.assertTrue(self.client.post(f'/api/period/{p1.id}/start').get_json()['ok'])
                self.assertEqual(self.mecz().status, self.Game.STATUS_PENDING)
                self.assertTrue(self.client.post(f'/api/period/{p1.id}/finish').get_json()['ok'])
                self.assertEqual(self.client.get('/api/wp-zapis/status').get_json()['niezakonczone'], [])            # jeszcze jest druga część
                self.assertTrue(self.client.post(f'/api/period/{p2.id}/start').get_json()['ok'])
                odp = self.client.post(f'/api/period/{p2.id}/finish')
                self.assertTrue(odp.get_json()['ok'])
                self.assertTrue(odp.get_json()['all_finished'])
                self.assertEqual(self.mecz().status, self.Game.STATUS_PENDING)                                     # mecz NIE kończy się sam
                nz = self.client.get('/api/wp-zapis/status').get_json()['niezakonczone']
                self.assertEqual([x['game_id'] for x in nz], [self.g1])
                self.assertEqual(self.client.post(f'/api/games/{self.g1}/finish').get_json()['status'], self.Game.STATUS_FINISHED)
                self.assertEqual(self.client.get('/api/wp-zapis/status').get_json()['niezakonczone'], [])
                self.wyslij()
                cialo = self.fake.zapytania[-1][1]
                self.assertEqual(cialo['state'], 'zakonczony')
            finally:
                cm._hub_client = None
                cm._timer_manager = None

        def test_start_zegara_glownego_rozpoczyna_mecz_i_trafia_do_wp(self):
            """Wymaganie właściciela: mecz trwa od wciśnięcia START zegara (potwierdzenie z timer-pluginu), niezależnie od drogi startu."""
            from unittest.mock import MagicMock
            import core.managers as cm
            from core.managers.period_manager import PeriodManager
            from app.managers.timer_manager import TimerManager
            from app.models import Period, GameTimer
            cm._hub_client = MagicMock()
            tm = TimerManager(cm._hub_client)
            tm._broadcast_penalty_state = lambda *a, **k: None
            cm._timer_manager = tm
            try:
                PeriodManager().create_default_periods(game_id=self.g1)
                p1 = Period.query.filter_by(game_id=self.g1).order_by(Period.period_order).first()
                self.db.session.add(GameTimer(game_id=self.g1, period_id=p1.id, timer_type=GameTimer.TYPE_MAIN, plugin_timer_id=p1.main_timer_name,
                                              elapsed_time_ms=0, limit_ms=p1.limit, state='idle'))
                self.db.session.commit()
                self.assertEqual((self.mecz().status, p1.status), (self.Game.STATUS_NOT_STARTED, Period.STATUS_NOT_STARTED))
                tm.on_timer_started({'type': 'timer_started', 'payload': {'timer_id': p1.main_timer_name, 'state': 'running', 'elapsed_time': 0, 'limit': p1.limit}})
                self.assertEqual(self.mecz().status, self.Game.STATUS_PENDING)
                self.assertEqual(self.wyslij(), 1)
                self.assertEqual(self.fake.zapytania[-1][1]['state'], 'trwa')
                self.zmien(status=self.Game.STATUS_FINISHED)                                                 # mecz zakończony nie wraca do „trwa” przez zegar
                tm.on_timer_started({'type': 'timer_started', 'payload': {'timer_id': p1.main_timer_name, 'state': 'running', 'elapsed_time': 0, 'limit': p1.limit}})
                self.assertEqual(self.mecz().status, self.Game.STATUS_FINISHED)
            finally:
                cm._hub_client = None
                cm._timer_manager = None

        def test_okno_zakonczenia_zna_remis_bez_rozstrzygniecia_w_pucharze(self):
            from unittest.mock import MagicMock
            import core.managers as cm
            import core.managers.session_manager as sm
            from core.managers.period_manager import PeriodManager
            from app.managers.timer_manager import TimerManager
            from app.models import Period, League
            cm._hub_client = MagicMock()
            tm = TimerManager(cm._hub_client)
            tm._broadcast_penalty_state = lambda *a, **k: None
            cm._timer_manager = tm
            try:
                self.db.session.get(League, self.mecz().league_id).allows_draw = False                          # liga bez remisów (puchar)
                self.db.session.commit()
                PeriodManager().create_default_periods(game_id=self.g1)
                sm.activate_game(self.g1)
                for p in Period.query.filter_by(game_id=self.g1).order_by(Period.period_order).all():
                    p.status = Period.STATUS_FINISHED
                self.db.session.commit()
                self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=2, away_team_goals=2)
                nz = self.client.get('/api/wp-zapis/status').get_json()['niezakonczone']
                self.assertTrue(nz and nz[0]['remis_bez_rozstrzygniecia'])
            finally:
                cm._hub_client = None
                cm._timer_manager = None

        def test_zakonczenie_meczu_przez_zmiane_statusu_w_zakladce_mecze_dziala_bez_okna(self):
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=1, away_team_goals=1)
            odp = self.client.patch(f'/api/games/{self.g1}/status', json={'status': 2})
            self.assertTrue(odp.get_json()['ok'])
            self.assertEqual(self.mecz().status, self.Game.STATUS_FINISHED)

        def test_zakonczenie_nieistniejacego_meczu_to_404_a_powtorne_jest_bezpieczne(self):
            self.assertEqual(self.client.post('/api/games/99999/finish').status_code, 404)
            self.zmien(status=self.Game.STATUS_PENDING, home_team_goals=0, away_team_goals=0)
            self.client.post(f'/api/games/{self.g1}/finish')
            self.assertEqual(self.client.post(f'/api/games/{self.g1}/finish').get_json()['status'], self.Game.STATUS_FINISHED)

    return ZapisDoWp


def make_node():
    """Pasek zapisu, pasek „Mecz nie jest zakończony” i okno „Zakończyć mecz?” (prawdziwy kod wp-zapis.js w Node): wchodzi do zestawu modułu."""
    import shutil
    import subprocess

    class WpZapisUiNode(unittest.TestCase):
        def test_wp_zapis_ui_w_node(self):
            node = shutil.which('node')
            if node is None:
                raise RuntimeError('Brak Node.js w PATH')
            skrypt = Path(__file__).resolve().parent / 'js' / 'wp_zapis_ui_test.js'
            r = subprocess.run([node, str(skrypt)], capture_output=True, text=True, encoding='utf-8', timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('OK 5 przypadków', r.stdout)

    return WpZapisUiNode
