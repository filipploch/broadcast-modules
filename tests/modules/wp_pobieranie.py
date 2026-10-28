"""W7a: pobieranie pary (liga, sezon) z WP do bazy modułu (core/managers/wp_pull.py).

Atrapa WP udaje trasy SportsPressa (teams, players, events z filtrami leagues/seasons/include i stronicowaniem) w kształcie prawdziwych odpowiedzi
(tytuł w "rendered", "main_results", "day" jako tekst, pola własne w "meta"). Wspólne dla obu modułów; każdy moduł woła make(APP)."""
import json
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import harness
from wp_rozgrywki import make_cfg

L, S = 1, 10             # liga i sezon pary w atrapie


class FakeWpPull:
    def __init__(self):
        self.leagues = [{'id': L, 'name': 'Dywizja A', 'slug': 'dywizja-a'}, {'id': 2, 'name': 'Puchar Ligi', 'slug': 'puchar'}]
        self.seasons = [{'id': S, 'name': 'Jesień 2026', 'slug': 'jesien-2026'}]
        self.teams, self.players, self.events = [], [], []
        self.bledy = {}              # kolekcja -> kod HTTP albo 'zerwij'
        self.zapytania = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                route = (q.get('rest_route') or [''])[0].strip('/')
                par = {k: v[0] for k, v in q.items()}
                fake.zapytania.append((route, par))
                kol = route.rsplit('/', 1)[-1]
                data = {'leagues': fake.leagues, 'seasons': fake.seasons, 'teams': fake.teams, 'players': fake.players, 'events': fake.events}.get(kol)
                if data is None:
                    return self._send(404, {'code': 'rest_no_route'})
                blad = fake.bledy.get(kol)
                if blad == 'zerwij':
                    self.connection.close()
                    return
                if blad:
                    return self._send(blad, {'code': 'x'})
                if 'include' in par:
                    ids = {int(i) for i in par['include'].split(',')}
                    data = [x for x in data if x['id'] in ids]
                for tax in ('leagues', 'seasons'):
                    if tax in par and kol in ('teams', 'players', 'events'):
                        data = [x for x in data if int(par[tax]) in x.get(tax, [])]
                if 'publish,future' not in par.get('status', 'publish,future'):
                    data = [x for x in data if x.get('status', 'publish') == 'publish']
                per, page = int(par.get('per_page', 10)), int(par.get('page', 1))
                pages = max(1, -(-len(data) // per))
                self._send(200, data[(page - 1) * per: page * per], {'X-WP-TotalPages': str(pages)})

            def _send(self, code, body, headers=None):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def team(self, tid, nazwa, short=None, n14=None, logo=None, leagues=(L,), seasons=(S,)):
        meta = {k: v for k, v in (('bm_short_name', short), ('bm_name14', n14), ('bm_logo', logo)) if v is not None}
        self.teams.append({'id': tid, 'title': {'rendered': nazwa}, 'meta': meta, 'abbreviation': '', 'leagues': list(leagues), 'seasons': list(seasons),
                           'status': 'publish'})

    def player(self, pid, tytul, teams, number='', first=None, last=None, leagues=(L,), seasons=(S,), current=None, past=None):
        """current/past: drużyny aktualne i dawne (SportsPress); bez nich rekord ma tylko wspólną listę 'teams' jak po starym imporcie."""
        meta = {k: v for k, v in (('bm_first_name', first), ('bm_last_name', last)) if v is not None}
        rekord = {'id': pid, 'title': {'rendered': tytul}, 'number': number, 'teams': list(teams), 'meta': meta,
                  'leagues': list(leagues), 'seasons': list(seasons), 'status': 'publish'}
        if current is not None or past is not None:
            rekord['current_teams'], rekord['past_teams'] = list(current or []), list(past or [])
            rekord['teams'] = list(dict.fromkeys([*rekord['current_teams'], *rekord['past_teams']]))
        self.players.append(rekord)

    def event(self, eid, teams, date='2026-09-05T12:00:00', wynik=None, day='1', live=False, locked=False, leagues=(L,), seasons=(S,), tytul=None):
        self.events.append({'id': eid, 'title': {'rendered': tytul or 'A &#8211; B'}, 'date': date, 'status': 'publish' if wynik else 'future',
                            'teams': list(teams), 'main_results': [str(wynik[0]), str(wynik[1])] if wynik else [], 'day': day,
                            'meta': {'bm_live': live, 'bm_locked': locked}, 'leagues': list(leagues), 'seasons': list(seasons)})

    def znajdz(self, kol, wid):
        return next(x for x in getattr(self, kol) if x['id'] == wid)


def wypelnij(wp):
    """Typowa para: 4 drużyny, 5 zawodników, 4 mecze (2 z wynikiem, 1 do rozegrania, 1 „Do ustalenia”)."""
    wp.team(101, 'Garbarnia Kraków', short='GAR', n14='Garbarnia', logo='modul/Garbarnia.png')
    wp.team(102, 'KS Chełmek', short='CHE', n14='Chełmek', logo='modul/Chelmek.png')
    wp.team(103, 'Żarłacze', short='ŻAR', logo='modul/Brak.png')              # skrót z polską literą; plik logo nie istnieje
    wp.team(104, 'Nowa Drużyna Bez Skrótu')                                   # bez pól własnych: wartości wyliczone
    wp.player(301, 'Kowalski Jan', [101], number='7', first='Jan', last='Kowalski')
    wp.player(302, 'Van Dijk Piotr', [101], number='10', first='Piotr', last='Van Dijk')
    wp.player(303, 'Nowak Adam', [102], number='')
    wp.player(304, 'Wieloczłonowy Anna Maria', [103])
    wp.player(305, 'Obcy Zawodnik', [999])                                    # drużyna poza parą
    wp.event(201, [101, 102], '2026-09-05T12:00:00', wynik=(3, 1), day='1', tytul='Garbarnia &#8211; Chełmek')
    wp.event(202, [103, 104], '2026-09-12T18:30:00', wynik=(0, 0), day='2')
    wp.event(203, [102, 103], '2026-09-19T20:00:00', day='3')
    wp.event(204, [0, 0], '2026-10-03T20:00:00', day='Finał', tytul='Do ustalenia &#8211; Do ustalenia')
    return wp


def make(APP):
    from sqlalchemy import event as sa_event

    class Podstawa(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)
            self.wp = wypelnij(FakeWpPull())
            self.tmp = Path(tempfile.mkdtemp(prefix='bm-pull-'))
            self.logos = self.tmp / 'logos'
            (self.logos / 'modul').mkdir(parents=True)
            for f in ('Garbarnia.png', 'Chelmek.png', 'default.png'):
                (self.logos / 'modul' / f).write_bytes(b'png')
            (self.logos / 'default.png').write_bytes(b'png')
            self.ctx = APP.app_context()
            self.ctx.push()
            from core.extensions import db
            from app.models import Stadium
            self.db = db
            db.session.add(Stadium(name='Hala', address='ul. Testowa 1', city='Krakow'))
            db.session.commit()
            self.kopie = self.tmp / 'kopie-wp'

        def tearDown(self):
            self.db.session.remove()
            self.ctx.pop()
            self.wp.close()

        def pobierz(self, apply=True, liga=L, sezon=S, port=None):
            from core.managers.wp_client import WpClient
            from core.managers.wp_pull import pobierz_pare
            klient = WpClient(make_cfg(port or self.wp.port, 'u', 'p'), timeout=3)
            return pobierz_pare(klient, self.db, liga, sezon, self.logos, 'modul', self.kopie, apply)

        def modele(self):
            from app.models import Game, League, LeagueTeam, Player, Season, Team
            return Game, League, LeagueTeam, Player, Season, Team

        def licznik_zapisow(self):
            """Liczy instrukcje zapisujące bazę (INSERT/UPDATE/DELETE) wysłane od tej chwili."""
            wynik = []

            def nasluch(conn, cursor, statement, params, context, executemany):
                if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    wynik.append(statement.split()[0:3])
            sa_event.listen(self.db.engine, 'before_cursor_execute', nasluch)
            self.addCleanup(sa_event.remove, self.db.engine, 'before_cursor_execute', nasluch)
            return wynik

    class PierwszePobranie(Podstawa):
        def test_pobranie_zapisuje_sezon_lige_druzyny_zawodnikow_i_mecze(self):
            Game, League, LeagueTeam, Player, Season, Team = self.modele()
            wynik = self.pobierz()
            self.assertTrue(wynik['ok'], wynik)
            self.assertTrue(wynik['zapisano'])
            r = wynik['raport']
            self.assertEqual(r['liczniki']['druzyny']['dodano'], 4)
            self.assertEqual(r['liczniki']['zawodnicy']['dodano'], 4)           # Obcy Zawodnik pominięty
            self.assertEqual(r['liczniki']['zawodnicy']['pominieto'], 0)           # zawodnik spoza drużyn pary nie jest liczony
            self.assertEqual(r['liczniki']['mecze']['dodano'], 3)
            sezon = Season.query.one()
            liga = League.query.one()
            self.assertEqual((sezon.name, liga.name, liga.season_id, liga.allows_draw), ('Jesień 2026', 'Dywizja A', sezon.id, True))
            self.assertEqual(LeagueTeam.query.filter_by(league_id=liga.id).count(), 4)

        def test_pola_druzyn_nazwa14_skrot_logo(self):
            self.pobierz()
            Team = self.modele()[5]
            g = Team.query.filter_by(name='Garbarnia Kraków').one()
            self.assertEqual((g.name_14, g.short_name, g.logo_path), ('Garbarnia', 'GAR', 'static/images/logos/modul/Garbarnia.png'))
            z = Team.query.filter_by(name='Żarłacze').one()
            self.assertEqual(z.short_name, 'ŻAR')                                    # skrót z WP bez zmian, także z polską literą
            self.assertEqual(z.logo_path, 'static/images/logos/modul/default.png')   # brak pliku logo = default.png folderu modułu
            n = Team.query.filter_by(name='Nowa Drużyna Bez Skrótu').one()
            self.assertEqual((n.short_name, n.name_14), ('NOW', 'Nowa Drużyna'))     # skrót wyliczony; nazwa 14 na granicy słowa
            self.assertEqual(n.logo_path, 'static/images/logos/modul/default.png')

        def test_raport_wymienia_wyliczone_skroty_i_brak_logo(self):
            r = self.pobierz()['raport']
            self.assertEqual(r['skroty_wyliczone'], ['Nowa Drużyna Bez Skrótu → NOW'])
            self.assertTrue(any('Żarłacze' in x and 'default.png' in x for x in r['brak_logo']))

        def test_zawodnicy_imie_i_nazwisko_z_pol_albo_z_podzialu_tytulu(self):
            self.pobierz()
            Player = self.modele()[3]
            ludzie = {(p.last_name, p.first_name): p for p in Player.query}
            self.assertEqual(ludzie[('Kowalski', 'Jan')].number, 7)
            self.assertIn(('Van Dijk', 'Piotr'), ludzie)                             # pola własne ważniejsze niż dzielenie tytułu
            self.assertIsNone(ludzie[('Nowak', 'Adam')].number)
            self.assertIn(('Wieloczłonowy Anna', 'Maria'), ludzie)                   # bez pól własnych: ostatni wyraz to imię
            self.assertEqual(ludzie[('Kowalski', 'Jan')].team.name, 'Garbarnia Kraków')

        def test_mecze_wynik_status_data_i_runda(self):
            self.pobierz()
            Game = self.modele()[0]
            m = {g.home_team.name: g for g in Game.query}
            g = m['Garbarnia Kraków']
            self.assertEqual((g.home_team_goals, g.away_team_goals, g.status, g.round), (3, 1, Game.STATUS_FINISHED, 1))
            self.assertEqual(g.date, datetime(2026, 9, 5, 12, 0))
            g0 = m['Żarłacze']
            self.assertEqual((g0.home_team_goals, g0.away_team_goals, g0.status), (0, 0, Game.STATUS_FINISHED))   # 0:0 to wynik
            g3 = m['KS Chełmek']
            self.assertEqual((g3.home_team_goals, g3.status, g3.round), (None, Game.STATUS_NOT_STARTED, 3))

        def test_mecz_do_ustalenia_nie_powstaje_i_nie_powstaje_druzyna(self):
            wynik = self.pobierz()
            Game, _, _, _, _, Team = self.modele()
            r = wynik['raport']
            self.assertEqual(r['do_ustalenia_liczba'], 1)
            self.assertEqual(Game.query.count(), 3)
            self.assertFalse(Team.query.filter(Team.name.like('%ustalenia%')).count())
            self.assertIn('Do ustalenia', r['do_ustalenia'][0])

        def test_powtorzenie_nie_zmienia_i_nie_zapisuje_nic(self):
            self.pobierz()
            zapisy = self.licznik_zapisow()
            wynik = self.pobierz()
            self.assertFalse(wynik['zapisano'])
            r = wynik['raport']
            self.assertFalse(r['zmieniono'])
            for k in ('druzyny', 'zawodnicy', 'mecze'):
                self.assertEqual((r['liczniki'][k]['dodano'], r['liczniki'][k]['zaktualizowano']), (0, 0), k)
            self.assertEqual(zapisy, [])

        def test_po_uzupelnieniu_par_w_wp_nastepne_pobranie_wczytuje_mecz(self):
            self.pobierz()
            self.wp.znajdz('events', 204)['teams'] = [101, 104]
            r = self.pobierz()['raport']
            self.assertEqual((r['liczniki']['mecze']['dodano'], r['do_ustalenia_liczba']), (1, 0))

        def test_podglad_niczego_nie_zapisuje_a_zapis_robi_to_co_pokazal_podglad(self):
            Game = self.modele()[0]
            zapisy = self.licznik_zapisow()
            podglad = self.pobierz(apply=False)
            self.assertEqual((podglad['zapisano'], zapisy, Game.query.count()), (False, [], 0))
            self.assertEqual(podglad['raport']['liczniki']['mecze']['dodano'], 3)
            self.assertEqual(self.kopie.exists(), False)
            zapis = self.pobierz()
            self.assertEqual(zapis['raport']['liczniki'], podglad['raport']['liczniki'])
            self.assertEqual(Game.query.count(), 3)

    class ReguleMeczow(Podstawa):
        def setUp(self):
            super().setUp()
            self.pobierz()
            from app.models import Game
            self.Game = Game
            self.g1 = Game.query.filter_by(home_team_id=self.team('Garbarnia Kraków').id).one()
            self.g2 = Game.query.filter_by(home_team_id=self.team('Żarłacze').id).one()
            self.g3 = Game.query.filter_by(home_team_id=self.team('KS Chełmek').id).one()

        def team(self, nazwa):
            return self.modele()[5].query.filter_by(name=nazwa).one()

        def test_mecz_nierozpoczety_dostaje_zmiany_z_wp(self):
            self.wp.znajdz('events', 203)['date'] = '2026-09-26T19:00:00'
            self.wp.znajdz('events', 203)['main_results'] = ['2', '2']
            r = self.pobierz()['raport']
            self.db.session.refresh(self.g3)
            self.assertEqual((self.g3.home_team_goals, self.g3.away_team_goals, self.g3.status), (2, 2, self.Game.STATUS_FINISHED))
            self.assertEqual(self.g3.date, datetime(2026, 9, 26, 19, 0))
            self.assertEqual(r['liczniki']['mecze']['zaktualizowano'], 1)

        def test_mecz_w_toku_w_module_jest_pomijany(self):
            self.g3.status = self.Game.STATUS_PENDING
            self.db.session.commit()
            self.wp.znajdz('events', 203)['main_results'] = ['5', '0']
            r = self.pobierz()['raport']
            self.db.session.refresh(self.g3)
            self.assertEqual((self.g3.home_team_goals, self.g3.status), (None, self.Game.STATUS_PENDING))
            self.assertEqual(len(r['pominiete']), 1)
            self.assertIn('trwa', r['pominiete'][0])

        def test_mecz_z_bm_live_w_wp_jest_pomijany(self):
            self.wp.znajdz('events', 203)['meta']['bm_live'] = True
            self.wp.znajdz('events', 203)['main_results'] = ['5', '0']
            r = self.pobierz()['raport']
            self.db.session.refresh(self.g3)
            self.assertEqual(self.g3.home_team_goals, None)
            self.assertEqual(len(r['pominiete']), 1)

        def test_mecz_aktywny_w_otwartej_sesji_jest_pomijany(self):
            from app.models import BroadcastSession, SessionGame
            s = BroadcastSession(status='live', open_slot=1)
            self.db.session.add(s)
            self.db.session.flush()
            self.db.session.add(SessionGame(session_id=s.id, game_id=self.g3.id, position=1, status='active', active_slot=1))
            self.db.session.commit()
            self.wp.znajdz('events', 203)['main_results'] = ['5', '0']
            r = self.pobierz()['raport']
            self.db.session.refresh(self.g3)
            self.assertEqual(self.g3.home_team_goals, None)
            self.assertIn('sesji', r['pominiete'][0])

        def test_mecz_rozpoczety_w_module_ale_niezakonczony_jest_pomijany(self):
            from app.models import Period
            self.db.session.add(Period(game_id=self.g3.id, period_order=1, description='1. połowa'))
            self.db.session.commit()
            self.wp.znajdz('events', 203)['main_results'] = ['5', '0']
            r = self.pobierz()['raport']
            self.db.session.refresh(self.g3)
            self.assertEqual(self.g3.home_team_goals, None)
            self.assertIn('rozpoczęty', r['pominiete'][0])

        def test_zakonczony_mecz_dostaje_korekte_wyniku_z_jawnym_wpisem(self):
            self.wp.znajdz('events', 201)['main_results'] = ['3', '2']
            r = self.pobierz()['raport']
            self.db.session.refresh(self.g1)
            self.assertEqual((self.g1.home_team_goals, self.g1.away_team_goals), (3, 2))
            self.assertEqual(len(r['korekty']), 1)
            self.assertIn('moduł 3:1 → WP 3:2', r['korekty'][0])

        def test_wp_bez_wyniku_nie_kasuje_wyniku_zakonczonego_w_module(self):
            ev = self.wp.znajdz('events', 201)
            ev['main_results'] = []
            ev['status'] = 'future'
            r = self.pobierz()['raport']
            self.db.session.refresh(self.g1)
            self.assertEqual((self.g1.home_team_goals, self.g1.away_team_goals, self.g1.status), (3, 1, self.Game.STATUS_FINISHED))
            self.assertEqual(r['korekty'], [])

        def test_zmiana_druzyn_w_zakonczonym_meczu_to_rozbieznosc_bez_zmiany(self):
            self.wp.znajdz('events', 201)['teams'] = [101, 104]
            r = self.pobierz()['raport']
            self.db.session.refresh(self.g1)
            self.assertEqual(self.g1.away_team.name, 'KS Chełmek')
            self.assertTrue(any('inne drużyny' in x for x in r['rozbieznosci']))

        def test_nigdy_nie_usuwa_i_raportuje_rekordy_nieobecne_w_wp(self):
            wp = self.wp
            wp.events[:] = [e for e in wp.events if e['id'] != 203]
            wp.players[:] = [p for p in wp.players if p['id'] != 301]
            wp.teams[:] = [t for t in wp.teams if t['id'] != 104]
            wp.events[:] = [e for e in wp.events if e['id'] not in (202, 204)]
            r = self.pobierz()['raport']
            self.assertEqual(self.Game.query.count(), 3)
            self.assertEqual(self.modele()[3].query.count(), 4)
            self.assertEqual(self.modele()[5].query.count(), 4)
            tekst = ' | '.join(r['nieobecne'])
            self.assertIn('Chełmek', tekst)
            self.assertIn('Kowalski Jan', tekst)
            self.assertIn('Nowa Drużyna Bez Skrótu', tekst)

        def test_zawodnik_przeniesiony_do_innej_druzyny_dostaje_nowe_team_id(self):
            self.wp.znajdz('players', 301)['teams'] = [102]
            self.pobierz()
            p = self.modele()[3].query.filter_by(last_name='Kowalski').one()
            self.assertEqual(p.team.name, 'KS Chełmek')

    class AktualneIDawneDruzyny(Podstawa):
        """W7e-1: do puli pary należy zawodnik z AKTUALNĄ drużyną w parze; dawne drużyny się nie liczą."""

        def _zawodnik(self, current, past, nr=399, nazwa='Wolnicki Piotr'):
            self.wp.player(nr, nazwa, [], first='Piotr', last='Wolnicki', current=current, past=past)

        def _gracz(self, nazwisko):
            return self.modele()[3].query.filter_by(last_name=nazwisko).first()

        def test_jedna_aktualna_druzyna_przypisanie_automatyczne_a_dawna_nie_liczy_sie(self):
            self._zawodnik([102], [101])
            r = self.pobierz()['raport']
            self.assertEqual(self._gracz('Wolnicki').team.name, 'KS Chełmek')
            self.assertFalse(any('Wolnicki' in x for x in r['kilka_aktualnych'] + r['tylko_dawne']))
            self.assertGreaterEqual(r['przynaleznosc']['jedna'], 1)

        def test_tylko_dawne_w_parze_zawodnik_nie_wchodzi_do_puli_i_jest_w_raporcie(self):
            self._zawodnik([], [101, 102])
            self.wp.player(398, 'Inny Adam', [], first='Adam', last='Inny', current=[777], past=[101])          # aktualna drużyna poza parą
            r = self.pobierz()['raport']
            self.assertIsNone(self._gracz('Wolnicki'))
            self.assertIsNone(self._gracz('Inny'))
            self.assertEqual(r['przynaleznosc']['tylko_dawne'], 2)
            self.assertTrue(any('Wolnicki' in x and 'Garbarnia Kraków' in x and 'KS Chełmek' in x for x in r['tylko_dawne']))
            self.assertTrue(any('Inny' in x and 'poza parą: 1' in x for x in r['tylko_dawne']))

        def test_kilka_aktualnych_w_parze_wybor_deterministyczny_i_lista_z_nazwami(self):
            self._zawodnik([102, 101], [])
            r = self.pobierz()['raport']
            self.assertEqual(self._gracz('Wolnicki').team.name, 'Garbarnia Kraków')                    # najniższy numer WP w parze (101)
            wpis = next(x for x in r['kilka_aktualnych'] if 'Wolnicki' in x)
            self.assertIn('Garbarnia Kraków', wpis)
            self.assertIn('KS Chełmek', wpis)
            self.assertIn('przypisano: Garbarnia Kraków', wpis)
            self.assertEqual(r['przynaleznosc']['kilka'], 1)

        def test_obecna_druzyna_modulu_zostaje_jesli_wp_nadal_ja_wymienia_jako_aktualna(self):
            self._zawodnik([102], [])
            self.pobierz()
            self.assertEqual(self._gracz('Wolnicki').team.name, 'KS Chełmek')
            self.wp.znajdz('players', 399)['current_teams'] = [101, 102]
            self.wp.znajdz('players', 399)['teams'] = [101, 102]
            r = self.pobierz()['raport']
            self.assertEqual(self._gracz('Wolnicki').team.name, 'KS Chełmek')                          # zostaje, mimo że 101 jest „pierwsza” po numerze WP
            self.assertEqual(r['przynaleznosc']['kilka'], 1)

        def test_gdy_wp_nie_wymienia_juz_obecnej_druzyny_jako_aktualnej_zawodnik_przechodzi(self):
            self._zawodnik([101], [])
            self.pobierz()
            self.assertEqual(self._gracz('Wolnicki').team.name, 'Garbarnia Kraków')
            self.wp.znajdz('players', 399)['current_teams'] = [102]
            self.wp.znajdz('players', 399)['past_teams'] = [101]
            self.pobierz()
            self.assertEqual(self._gracz('Wolnicki').team.name, 'KS Chełmek')

        def test_zawodnik_ktory_stal_sie_tylko_dawnym_w_parze_zostaje_w_module_bez_druzyny_i_jest_zwolniony(self):
            self._zawodnik([101], [])
            self.pobierz()
            self.wp.znajdz('players', 399)['current_teams'] = [777]
            self.wp.znajdz('players', 399)['past_teams'] = [101]
            r = self.pobierz()['raport']
            self.assertIsNotNone(self._gracz('Wolnicki'))                                                # nigdy nie usuwamy
            self.assertIsNone(self._gracz('Wolnicki').team_id)                                           # W7e-1: zwolniony z drużyny (WP jej już nie wymienia)
            self.assertTrue(any('Wolnicki' in x for x in r['zwolnieni']))

        # -- zwolnienie z drużyny: WP nie wymienia już drużyny pary jako aktualnej
        def _gry(self):
            Game = self.modele()[0]
            return Game.query.order_by(Game.date).all()

        def _dodaj_do_skladu(self, gracz, gra):
            from app.models import GamePlayer
            self.db.session.add(GamePlayer(player_id=gracz.id, game_id=gra.id, team_id=gracz.team_id, number=7))
            self.db.session.commit()

        def _zwolnij_wp(self, current, past):
            self.wp.znajdz('players', 399)['current_teams'] = list(current)
            self.wp.znajdz('players', 399)['past_teams'] = list(past)
            self.wp.znajdz('players', 399)['teams'] = list(dict.fromkeys([*current, *past]))

        def test_zwolniony_z_druzyny_bez_innej_aktualnej_w_module_zostaje_bez_druzyny_i_rekord_zostaje(self):
            self._zawodnik([101], [])
            self.pobierz()
            self._zwolnij_wp([777], [101])
            r = self.pobierz()['raport']
            gracz = self._gracz('Wolnicki')
            self.assertIsNotNone(gracz)                                                           # nigdy nie usuwamy
            self.assertIsNone(gracz.team_id)
            self.assertTrue(any('Wolnicki' in x and 'zwolniony z drużyny Garbarnia Kraków' in x and 'bez drużyny' in x for x in r['zwolnieni']))
            self.assertFalse(any('Wolnicki' in x for x in r['nieobecne']))                       # nie dublujemy w „nieobecnych”
            self.assertEqual(r['przynaleznosc']['tylko_dawne'], 1)

        def test_zwolniony_przechodzi_do_aktualnej_druzyny_z_wp_ktora_jest_w_module(self):
            self.wp.team(150, 'Puchar FC', short='PFC', leagues=(2,))
            self._zawodnik([101], [])
            self.pobierz()
            self.pobierz(liga=2)                                                                   # drużyna 150 trafia do modułu (inna para)
            self._zwolnij_wp([150], [101])
            r = self.pobierz()['raport']
            self.assertEqual(self._gracz('Wolnicki').team.name, 'Puchar FC')
            self.assertTrue(any('teraz: Puchar FC' in x for x in r['zwolnieni']))

        def test_zwolnienie_nie_zmienia_historii_skladu_meczowego_a_mecz_nierozpoczety_jest_w_raporcie(self):
            from app.models import GamePlayer
            self._zawodnik([101], [])
            self.pobierz()
            gracz, g1, g3 = self._gracz('Wolnicki'), self._gry()[0], self._gry()[2]
            team_przed = gracz.team_id
            self._dodaj_do_skladu(gracz, g1)                                                       # mecz zakończony
            self._dodaj_do_skladu(gracz, g3)                                                       # mecz nierozpoczęty
            self._zwolnij_wp([777], [101])
            r = self.pobierz()['raport']
            self.assertIsNone(self._gracz('Wolnicki').team_id)
            self.assertEqual({pg.team_id for pg in GamePlayer.query.filter_by(player_id=gracz.id)}, {team_przed})   # zdjęcie drużyny w składach zostaje
            wpis = next(x for x in r['zwolnieni'] if 'Wolnicki' in x)
            self.assertIn('nadal w kadrze meczu nierozpoczętego', wpis)

        def test_zwolnienie_wstrzymane_gdy_zawodnik_jest_w_kadrze_meczu_rozpoczetego_w_module(self):
            from app.models import Period
            self._zawodnik([101], [])
            self.pobierz()
            gracz, g3 = self._gracz('Wolnicki'), self._gry()[2]
            self._dodaj_do_skladu(gracz, g3)
            self.db.session.add(Period(game_id=g3.id, period_order=1, description='1. połowa'))
            self.db.session.commit()
            team_przed = gracz.team_id
            self._zwolnij_wp([777], [101])
            r = self.pobierz()['raport']
            self.assertEqual(self._gracz('Wolnicki').team_id, team_przed)
            self.assertTrue(any('Wolnicki' in x and 'trwa albo jest rozpoczęty' in x for x in r['zwolnieni']))

        def test_podglad_zwolnienia_niczego_nie_zapisuje_ale_wypisuje_zwolnionego(self):
            self._zawodnik([101], [])
            self.pobierz()
            team_przed = self._gracz('Wolnicki').team_id
            self._zwolnij_wp([777], [101])
            zapisy = self.licznik_zapisow()
            r = self.pobierz(apply=False)['raport']
            self.assertEqual(zapisy, [])
            self.assertEqual(self._gracz('Wolnicki').team_id, team_przed)
            self.assertTrue(any('Wolnicki' in x for x in r['zwolnieni']))

        def test_powtorne_pobranie_nie_zmienia_klasyfikacji_ani_bazy(self):
            self._zawodnik([102, 101], [])
            self._zawodnik([103], [101], nr=397, nazwa='Dawny Jan')
            self.pobierz()
            r = self.pobierz()['raport']
            self.assertFalse(r['zmieniono'])

    class KrawedzieIAwarie(Podstawa):
        def test_dwie_druzyny_o_tej_samej_nazwie_druga_dostaje_koncowke(self):
            self.wp.team(105, 'Garbarnia Kraków', short='GA2')
            r = self.pobierz()['raport']
            nazwy = sorted(t.name for t in self.modele()[5].query)
            self.assertIn('Garbarnia Kraków (2)', nazwy)
            self.assertTrue(any('nazwa zajęta' in x for x in r['rozbieznosci']))

        def test_encje_html_w_nazwach_sa_zamieniane(self):
            self.wp.team(105, 'Rock &amp; Roll &#8211; Team', short='ROC')
            self.pobierz()
            self.assertIsNotNone(self.modele()[5].query.filter_by(name='Rock & Roll – Team').first())

        def test_zawodnik_w_dwoch_druzynach_pary_trafia_do_pierwszej_i_jest_w_raporcie(self):
            self.wp.znajdz('players', 301)['teams'] = [102, 101]
            r = self.pobierz()['raport']
            p = self.modele()[3].query.filter_by(last_name='Kowalski').one()
            self.assertEqual(p.team.name, 'Garbarnia Kraków')
            self.assertTrue(any('Kowalski' in x and 'nie rozróżnia' in x for x in r['kilka_aktualnych']))
            self.assertEqual(r['przynaleznosc']['kilka'], 1)

        def test_kopia_pliku_bazy_nie_ginie_przez_obce_pliki_o_podobnej_nazwie_w_folderze_kopii(self):
            # regresja z W7d: kopie bazy „<nazwa>-proba-…” (inna baza) sortowały się „nowsze” i sprzątanie usuwało świeżą kopię
            from core.managers.wp_pull import kopia_bazy
            from types import SimpleNamespace
            import sqlite3
            baza = self.tmp / 'database.db'
            sqlite3.connect(str(baza)).close()
            fałszywa_baza = SimpleNamespace(engine=SimpleNamespace(url=SimpleNamespace(database=str(baza))))
            self.kopie.mkdir(parents=True, exist_ok=True)
            obce = [self.kopie / f'{baza.stem}-proba-20261028-00{i}000-000000.db' for i in range(6)]
            for f in obce:
                f.write_bytes(b'x')
            cel = kopia_bazy(fałszywa_baza, self.kopie)
            self.assertIsNotNone(cel)
            self.assertTrue(Path(cel).exists())                                                 # świeża kopia przeżyła sprzątanie
            self.assertTrue(all(f.exists() for f in obce))                                      # obcych plików nie ruszamy

        def test_nazwa_ligi_powyzej_50_znakow_jest_skracana_z_wpisem(self):
            self.wp.leagues[0]['name'] = 'Bardzo długa nazwa ligi która nie mieści się w pięćdziesięciu znakach'
            r = self.pobierz()['raport']
            self.assertEqual(len(self.modele()[1].query.one().name), 50)
            self.assertTrue(any('50 znaków' in x for x in r['rozbieznosci']))

        def test_numer_sezonu_jest_nastepnym_wolnym(self):
            from app.models import Season
            self.db.session.add(Season(number=30, name='Inny sezon'))
            self.db.session.commit()
            self.pobierz()
            self.assertEqual(Season.query.filter_by(name='Jesień 2026').one().number, 31)

        def test_istniejaca_druzyna_i_sezon_o_tej_samej_nazwie_sa_dolaczane(self):
            from app.models import Season, Team
            self.db.session.add_all([Season(number=5, name='Jesień 2026'), Team(name='KS Chełmek', name_14='Chełmek', short_name='CHM')])
            self.db.session.commit()
            r = self.pobierz()['raport']
            self.assertEqual(Season.query.count(), 1)
            self.assertEqual(Team.query.filter_by(name='KS Chełmek').count(), 1)
            self.assertEqual(Team.query.filter_by(name='KS Chełmek').one().short_name, 'CHE')    # skrót z WP nadpisuje
            self.assertEqual(len(r['dolaczono']), 2)

        def test_pucharowe_teksty_rund_i_nieznany_tekst_nie_wywracaja_nazwy_rundy(self):
            from core.utils.socketio_events_utils import _round_nr_to_round_name
            self.wp.leagues[0]['name'] = 'Puchar Ligi'
            for i, dzien in enumerate(['1/8 finału', 'Ćwierćfinał', 'Półfinał', 'Mecz o 3. miejsce', 'Finał', 'Coś dziwnego', '9']):
                self.wp.event(400 + i, [101, 102], f'2026-11-0{i + 1}T12:00:00', day=dzien)
            r = self.pobierz()['raport']
            Game = self.modele()[0]
            rundy = sorted((g.date, g.round) for g in Game.query if g.date.month == 11)
            self.assertEqual([x[1] for x in rundy], [2, 3, 4, 5, 6, 0, 0])
            for _, nr in rundy:
                _round_nr_to_round_name(nr, 'Puchar Ligi')                          # bez KeyError
            self.assertTrue(any('nieznany tekst rundy' in x for x in r['rozbieznosci']))
            self.assertTrue(any('poza zakresem' in x for x in r['rozbieznosci']))
            self.assertFalse(self.modele()[1].query.one().allows_draw)

        def test_pusty_dzien_to_runda_zero(self):
            self.wp.znajdz('events', 203)['day'] = ''
            self.pobierz()
            Game = self.modele()[0]
            self.assertEqual(Game.query.filter_by(home_team_id=self.modele()[5].query.filter_by(name='KS Chełmek').one().id).one().round, 0)

        def test_logo_ktorego_plik_zniknal_wraca_do_default_przy_kolejnym_pobraniu(self):
            self.pobierz()
            (self.logos / 'modul' / 'Garbarnia.png').unlink()
            r = self.pobierz()['raport']
            g = self.modele()[5].query.filter_by(name='Garbarnia Kraków').one()
            self.assertEqual(g.logo_path, 'static/images/logos/modul/default.png')
            self.assertTrue(any('Garbarnia' in x for x in r['brak_logo']))

        def test_brak_pola_logo_nie_nadpisuje_recznie_ustawionego(self):
            self.pobierz()
            Team = self.modele()[5]
            n = Team.query.filter_by(name='Nowa Drużyna Bez Skrótu').one()
            n.logo_path = '/static//images/logos/modul/Chelmek.png'
            self.db.session.commit()
            self.pobierz()
            self.db.session.refresh(n)
            self.assertEqual(n.logo_path, 'static/images/logos/modul/Chelmek.png')    # zachowane, w postaci kanonicznej

        def test_wartosc_skrotu_z_wp_dluzsza_niz_3_znaki_jest_obcinana_z_wpisem(self):
            self.wp.znajdz('teams', 101)['meta']['bm_short_name'] = 'GARB'
            r = self.pobierz()['raport']
            self.assertEqual(self.modele()[5].query.filter_by(name='Garbarnia Kraków').one().short_name, 'GAR')
            self.assertTrue(any('obcięty' in x for x in r['rozbieznosci']))

        def test_powtorzony_skrot_w_parze_jest_zglaszany(self):
            self.wp.znajdz('teams', 102)['meta']['bm_short_name'] = 'GAR'
            r = self.pobierz()['raport']
            self.assertTrue(any('powtórzony skrót „GAR”' in x for x in r['rozbieznosci']))

        def test_blad_w_polowie_zapisu_wycofuje_cala_transakcje(self):
            from core.managers import wp_pull
            Game, _, _, Player, Season, Team = self.modele()
            oryginal = wp_pull.Pobieranie._zawodnicy

            def zepsuty(self_, druzyny):
                if self_.apply:                                                     # podgląd przechodzi, awaria dopiero w trakcie zapisu
                    raise RuntimeError('awaria w polowie')
                return oryginal(self_, druzyny)
            wp_pull.Pobieranie._zawodnicy = zepsuty
            try:
                wynik = self.pobierz()
            finally:
                wp_pull.Pobieranie._zawodnicy = oryginal
            self.assertFalse(wynik['ok'])
            self.assertIn('baza bez zmian', wynik['blad'])
            self.assertEqual((Season.query.count(), Team.query.count(), Game.query.count(), Player.query.count()), (0, 0, 0, 0))
            self.assertEqual(len(list(self.kopie.glob('*.db'))), 1)                 # kopia powstała przed zapisem

        def test_zerwane_polaczenie_w_trakcie_odczytu_zostawia_baze_nietknieta(self):
            Season, Team = self.modele()[4], self.modele()[5]
            self.wp.bledy['events'] = 'zerwij'
            wynik = self.pobierz()
            self.assertFalse(wynik['ok'])
            self.assertIn('Pobieranie przerwane, baza bez zmian', wynik['blad'])
            self.assertEqual((Season.query.count(), Team.query.count()), (0, 0))

        def test_wp_niedostepny_daje_komunikat_a_baza_zostaje(self):
            port = self.wp.port
            self.wp.close()
            wynik = self.pobierz(port=port)
            self.assertFalse(wynik['ok'])
            self.assertIn('baza bez zmian', wynik['blad'])
            self.wp = FakeWpPull()                                                   # dla tearDown

        def test_para_usunieta_z_wp_daje_komunikat(self):
            wynik = self.pobierz(liga=99)
            self.assertFalse(wynik['ok'])
            self.assertIn('nie ma już w WP', wynik['blad'])

        def test_kopia_pliku_bazy_przed_zapisem_i_tylko_ostatnie_piec(self):
            for i in range(7):
                self.wp.event(500 + i, [101, 102], f'2026-12-0{i + 1}T12:00:00', day='4')
                wynik = self.pobierz()
                self.assertTrue(wynik['zapisano'])
                self.assertTrue(wynik['raport']['kopia'])
            self.assertEqual(len(list(self.kopie.glob('*.db'))), 5)

        def test_ten_sam_klient_nie_dotyka_drugiej_pary(self):
            self.wp.event(600, [101, 102], leagues=(2,), seasons=(S,))
            self.pobierz()
            Game = self.modele()[0]
            self.assertEqual(Game.query.count(), 3)

    class TrasaIPanel(Podstawa):
        def setUp(self):
            super().setUp()
            import core.managers as cm
            from core.managers.wp_manager import WpManager
            self.cm = cm
            self._saved = cm._wp_manager
            self._kopie_cfg = APP.config.get('WP_PULL_COPIES_DIR')
            APP.config['WP_PULL_COPIES_DIR'] = str(self.kopie)
            cm._wp_manager = WpManager(make_cfg(self.wp.port, 'u', 'p'), self.tmp / 'wp_rozgrywki.json')
            self.mgr = cm._wp_manager
            self.mgr.refresh()
            self.client = APP.test_client()
            # logo_root trasy to prawdziwy folder modułu; pliki logo z atrapy nie istnieją, więc drużyny dostaną default.png (sprawdzane osobno)

        def tearDown(self):
            self.cm._wp_manager = self._saved
            APP.config['WP_PULL_COPIES_DIR'] = self._kopie_cfg
            super().tearDown()

        def test_trasa_bez_wybranych_rozgrywek_zwraca_komunikat(self):
            self.mgr.clear_default()
            wynik = self.client.post('/api/wp/pull', json={'apply': False}).get_json()
            self.assertFalse(wynik['ok'])
            self.assertIn('wybierz rozgrywki', wynik['blad'])

        def test_podglad_i_pobranie_przez_trase_zapisuja_stan_dla_panelu(self):
            Game = self.modele()[0]
            podglad = self.client.post('/api/wp/pull', json={'apply': False, 'league_id': L, 'season_id': S}).get_json()
            self.assertTrue(podglad['ok'])
            self.assertEqual((podglad['zapisano'], Game.query.count()), (False, 0))
            st = self.client.get('/api/wp/state').get_json()
            self.assertEqual((st['pull']['apply'], st['pull']['key'], st['last_apply_at']), (False, '1:10', ''))
            wynik = self.client.post('/api/wp/pull', json={'apply': True, 'league_id': L, 'season_id': S}).get_json()
            self.assertTrue(wynik['zapisano'])
            self.assertEqual(Game.query.count(), 3)
            st = self.client.get('/api/wp/state').get_json()
            self.assertEqual((st['pull']['apply'], st['pull']['label'], st['pulling']), (True, 'Dywizja A — Jesień 2026', False))
            self.assertTrue(st['last_apply_at'])

        def test_pobranie_domyslnej_pary_gdy_nie_podano_numerow(self):
            self.mgr.set_default(L, S)
            wynik = self.client.post('/api/wp/pull', json={'apply': True}).get_json()
            self.assertTrue(wynik['ok'], wynik)
            self.assertEqual(wynik['key'], '1:10')

        def test_wynik_ostatniego_pobrania_przezywa_restart_menedzera(self):
            self.client.post('/api/wp/pull', json={'apply': True, 'league_id': L, 'season_id': S})
            from core.managers.wp_manager import WpManager
            drugi = WpManager(make_cfg(self.wp.port, 'u', 'p'), self.tmp / 'wp_rozgrywki.json')
            st = drugi.state()
            self.assertEqual((st['pull']['key'], bool(st['last_apply_at'])), ('1:10', True))

        def test_strona_rozgrywek_ma_przyciski_podgladu_i_pobrania(self):
            html = self.client.get('/wp/competitions').get_data(as_text=True)
            for needle in ('wp-preview', 'wp-pull', 'wp-pull-view.js', 'SPRAWDŹ ZMIANY', 'POBIERZ Z WP'):
                self.assertIn(needle, html)

        def test_stare_przyciski_pobierania_sa_ukryte_a_w_ich_miejscu_jeden_przycisk_z_wp(self):
            from app.models import League, Season, Team
            self.pobierz()
            liga = League.query.one()
            team = Team.query.first()
            flaga = APP.config.get('LEGACY_IMPORT_ENABLED')
            try:
                APP.config['LEGACY_IMPORT_ENABLED'] = False
                strony = [f'/leagues/{liga.id}/games/', f'/leagues/{liga.id}/teams', f'/teams/{team.id}/players']
                for url in strony:
                    html = self.client.get(url).get_data(as_text=True)
                    self.assertIn('Pobierz z WP', html, url)
                    self.assertIn('/wp/competitions', html, url)
                    self.assertNotIn('cascade-run-', html, url)
                    self.assertNotIn('startPlayerScraping', html, url)
                APP.config['LEGACY_IMPORT_ENABLED'] = True
                html = self.client.get(f'/leagues/{liga.id}/teams').get_data(as_text=True)
                self.assertNotIn('wp-pull-link', html)
            finally:
                APP.config['LEGACY_IMPORT_ENABLED'] = flaga

        def test_pusta_lista_meczow_podpowiada_pobranie_z_wp(self):
            from app.models import League, Season
            sezon = Season(number=1, name='Pusty sezon')
            self.db.session.add(sezon)
            self.db.session.flush()
            liga = League(season_id=sezon.id, name='Pusta liga', allows_draw=True)
            self.db.session.add(liga)
            self.db.session.commit()
            flaga = APP.config.get('LEGACY_IMPORT_ENABLED')
            try:
                APP.config['LEGACY_IMPORT_ENABLED'] = False
                html = self.client.get(f'/leagues/{liga.id}/games/').get_data(as_text=True)
                self.assertIn('Brak meczów.', html)
                self.assertIn('Pobierz z WP</a> ·', html)
            finally:
                APP.config['LEGACY_IMPORT_ENABLED'] = flaga

    class NazwyZWp(unittest.TestCase):
        """Te same przypadki co tests/import_wp/test_skroty.py: skrót wyliczony w narzędziu importu i w module ma być taki sam."""

        def test_skrot_z_nazwy(self):
            from core.utils.wp_names import wylicz_skrot
            self.assertEqual(wylicz_skrot('Garbarnia Kraków'), 'GAR')
            self.assertEqual(wylicz_skrot('KS Łagiewniki'), 'LAG')
            self.assertEqual(wylicz_skrot('Żurawie'), 'ZUR')
            self.assertEqual(wylicz_skrot('NO NAME NO GAME!'), 'NON')
            self.assertEqual(wylicz_skrot('16 Batalion'), '16B')
            self.assertEqual(wylicz_skrot('K2'), 'K2')

        def test_kolizje_i_zajete(self):
            from core.utils.wp_names import wylicz_unikalne
            w = wylicz_unikalne({1: 'Kabel Kraków', 2: 'Kabel Nowy'})
            self.assertEqual(len({v[0] for v in w.values()}), 2)
            self.assertTrue(any(v[1] for v in w.values()))
            z = wylicz_unikalne({1: 'Garbarnia'}, zajete=['GAR'])
            self.assertNotEqual(z[1][0], 'GAR')

        def test_nazwa_14_na_granicy_slowa(self):
            from core.utils.wp_names import nazwa_14
            self.assertEqual(nazwa_14('Garbarnia'), 'Garbarnia')
            self.assertEqual(nazwa_14('Nowa Drużyna Bez Skrótu'), 'Nowa Drużyna')
            self.assertEqual(nazwa_14('Bardzodługaniepodzielnanazwa'), 'Bardzodługanie')

        def test_podzial_nazwiska_i_numer_rundy(self):
            from core.utils.wp_names import numer_rundy, podziel_nazwisko_imie
            self.assertEqual(podziel_nazwisko_imie('Kędzior Grzegorz'), ('Kędzior', 'Grzegorz'))
            self.assertEqual(podziel_nazwisko_imie('Van Dijk Jan'), ('Van Dijk', 'Jan'))
            self.assertEqual(podziel_nazwisko_imie('Pele'), ('Pele', ''))
            self.assertEqual(numer_rundy('5'), (5, True))
            self.assertEqual(numer_rundy(''), (0, True))
            self.assertEqual(numer_rundy('Półfinał'), (4, True))
            self.assertEqual(numer_rundy('Mecz o 3. miejsce'), (5, True))
            self.assertEqual(numer_rundy('Coś'), (0, False))

    return PierwszePobranie, ReguleMeczow, KrawedzieIAwarie, TrasaIPanel, NazwyZWp, AktualneIDawneDruzyny
