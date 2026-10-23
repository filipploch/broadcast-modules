"""Etap I0: kopia i zerowanie danych rozgrywek (tools/import_wp/zerowanie.py) na tymczasowych bazach.

    python -m unittest discover tests/import_wp          (z katalogu głównego repozytorium)"""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'import_wp'))
import zerowanie  # noqa: E402

SCHEMA = """
create table alembic_version(version_num text);
create table scrapers(id integer primary key, folder text);
create table active_scraper_configs(id integer primary key, scraper_id integer references scrapers(id));
create table seasons(id integer primary key autoincrement, name text);
create table leagues(id integer primary key autoincrement, season_id integer references seasons(id), name text);
create table teams(id integer primary key autoincrement, name text, logo_path text);
create table players(id integer primary key autoincrement, team_id integer references teams(id), name text);
create table stadiums(id integer primary key, name text);
create table cameras(id integer primary key, name text);
create table games(id integer primary key autoincrement, home_team_id integer references teams(id), league_id integer references leagues(id),
                   stadium_id integer references stadiums(id));
create table game_events(id integer primary key autoincrement, game_id integer references games(id), player_id integer references players(id));
create table event_cameras(id integer primary key, game_event_id integer references game_events(id), camera_id integer references cameras(id));
create table game_cameras(id integer primary key, game_id integer references games(id), camera_id integer references cameras(id));
create table league_scraper_urls(id integer primary key, league_id integer references leagues(id), scraper_id integer references scrapers(id), url text);
create table league_foreign_ids(id integer primary key, league_id integer references leagues(id), scraper_id integer references scrapers(id), foreign_id text);
create table broadcast_sessions(id integer primary key autoincrement, status text);
create table session_games(id integer primary key, session_id integer references broadcast_sessions(id), game_id integer references games(id));
create table banners(id integer primary key, name text);
create table settings(id integer primary key, browse_season_id integer references seasons(id), is_scoreboard_reversed integer, obs_record_filepath text);
"""

DANE = """
insert into alembic_version values ('abc');
insert into scrapers values (1, 'nalffutsal');
insert into active_scraper_configs values (1, 1);
insert into seasons(name) values ('Jesień 2026');
insert into leagues(season_id, name) values (1, 'Dywizja A');
insert into teams(name, logo_path) values ('Alfa', '/static/images/logos/x/alfa.png'), ('Beta', 'static/images/logos/default.png');
insert into players(team_id, name) values (1, 'Jan');
insert into stadiums values (1, 'Hala');
insert into cameras values (1, 'cam1');
insert into games(home_team_id, league_id, stadium_id) values (1, 1, 1), (2, 1, 1);
insert into game_events(game_id, player_id) values (1, 1), (1, 1);
insert into event_cameras values (1, 1, 1), (2, 2, 1);
insert into game_cameras values (1, 1, 1);
insert into league_scraper_urls values (1, 1, 1, 'https://adres/terminarz');
insert into league_foreign_ids values (1, 1, 1, 'liga-a');
insert into broadcast_sessions(status) values ('closed');
insert into session_games values (1, 1, 1);
insert into banners values (1, 'baner');
insert into settings values (1, 1, 0, 'D:/Video/stary-mecz.mkv');
"""


def zrob_baze(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA + DANE)
    con.commit()
    con.close()


class AnalizaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='bm-zer-'))
        self.db = self.tmp / 'database.db'
        zrob_baze(self.db)

    def _analiza(self):
        con = zerowanie.polacz(self.db)
        try:
            return zerowanie.analiza(con)
        finally:
            con.close()

    def test_zerowane_sa_korzenie_zaleznosci_i_sesje_a_ustawienia_zostaja(self):
        a = self._analiza()
        self.assertEqual(sorted(a['zero']), sorted([
            'seasons', 'leagues', 'teams', 'players', 'games', 'game_events', 'event_cameras', 'game_cameras',
            'league_scraper_urls', 'league_foreign_ids', 'broadcast_sessions', 'session_games']))
        self.assertEqual(sorted(a['zostaje']), sorted([
            'alembic_version', 'scrapers', 'active_scraper_configs', 'stadiums', 'cameras', 'banners', 'settings']))
        self.assertEqual(sorted(a['settings_null']), ['browse_season_id', 'obs_record_filepath'])

    def test_powod_zaleznosci_jest_podany(self):
        a = self._analiza()
        self.assertIn('game_events', a['zero']['event_cameras'])
        self.assertIn('leagues', a['zero']['league_scraper_urls'])

    def test_zerowanie_czysci_dane_zostawia_ustawienia_i_resetuje_numeracje(self):
        r = zerowanie.zeruj_modul('x', self.db)
        con = sqlite3.connect(self.db)
        for t in r['zerowane']:
            self.assertEqual(con.execute(f'select count(*) from {t}').fetchone()[0], 0, t)
        for t, n in (('stadiums', 1), ('cameras', 1), ('banners', 1), ('scrapers', 1), ('active_scraper_configs', 1), ('alembic_version', 1), ('settings', 1)):
            self.assertEqual(con.execute(f'select count(*) from {t}').fetchone()[0], n, t)
        self.assertIsNone(con.execute('select browse_season_id from settings').fetchone()[0])
        self.assertIsNone(con.execute('select obs_record_filepath from settings').fetchone()[0])
        self.assertEqual(con.execute('select is_scoreboard_reversed from settings').fetchone()[0], 0)
        con.execute("insert into teams(name) values ('Nowa')")
        self.assertEqual(con.execute('select id from teams').fetchone()[0], 1)          # numeracja od początku
        con.close()
        self.assertEqual(r['przed']['games'], 2)
        self.assertEqual(r['po']['games'], 0)

    def test_eksport_adresow_niesie_nazwy_ligi_i_sezonu(self):
        con = zerowanie.polacz(self.db)
        try:
            eks = zerowanie.eksport_adresow(con)
        finally:
            con.close()
        self.assertEqual(eks['league_scraper_urls'][0]['url'], 'https://adres/terminarz')
        self.assertEqual(eks['league_scraper_urls'][0]['_liga'], {'liga': 'Dywizja A', 'sezon': 'Jesień 2026'})
        self.assertEqual(eks['league_scraper_urls'][0]['_scraper'], 'nalffutsal')
        self.assertEqual(eks['league_foreign_ids'][0]['foreign_id'], 'liga-a')


class KopiaTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='bm-zer-'))
        for m, port in (('futsal_nalf', 8091), ('garbarnia', 8092)):
            d = self.root / 'modules' / m
            (d / 'instance').mkdir(parents=True)
            zrob_baze(d / 'instance' / 'database.db')
            (d / 'instance' / 'wp_rozgrywki.json').write_text('{"default": null}', encoding='utf-8')
            (d / 'module.json').write_text(json.dumps({'format': 1, 'id': m, 'wp': {'port': port, 'title': m}}), encoding='utf-8')
            wp = self.root / 'wp-local' / 'databases' / f'p{port}'
            wp.mkdir(parents=True)
            (wp / '.ht.sqlite').write_bytes(f'baza {port}'.encode())
        (self.root / 'wp-local' / 'databases' / '_szablon').mkdir()
        (self.root / 'wp-local' / 'databases' / '_szablon' / '.ht.sqlite').write_bytes(b'szablon')
        logo = self.root / 'modules' / 'static' / 'images' / 'logos' / 'garbarnia'
        logo.mkdir(parents=True)
        (logo / 'a.png').write_bytes(b'png')
        self.patch = patch.object(zerowanie, 'REPO', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_kopia_zawiera_bazy_logo_wp_i_manifest(self):
        katalog, manifest = zerowanie.kopia(self.root / 'kopia')
        for m in zerowanie.MODULES:
            self.assertTrue((katalog / m / 'database.db').exists())
            self.assertTrue((katalog / m / 'wp_rozgrywki.json').exists())
            self.assertTrue((katalog / m / 'adresy_scraperow.json').exists())
        self.assertEqual((katalog / 'logos' / 'garbarnia' / 'a.png').read_bytes(), b'png')
        self.assertEqual((katalog / 'wp' / 'p8091' / '.ht.sqlite').read_bytes(), b'baza 8091')
        self.assertEqual(manifest['logo']['pliki'], 1)
        self.assertEqual(manifest['moduly']['garbarnia']['licznosci']['games'], 2)
        zerowanie.sprawdz_kopie(katalog)

    def test_kopia_nie_nadpisuje_istniejacej(self):
        zerowanie.kopia(self.root / 'kopia')
        with self.assertRaises(SystemExit):
            zerowanie.kopia(self.root / 'kopia')

    def test_zerowanie_bez_kopii_albo_z_uszkodzona_kopia_jest_odmowione(self):
        with self.assertRaises(SystemExit):
            zerowanie.zeruj_wszystko(self.root / 'brak')
        katalog, _ = zerowanie.kopia(self.root / 'kopia')
        (katalog / 'garbarnia' / 'database.db').write_bytes(b'zmieniona')
        with self.assertRaises(SystemExit):
            zerowanie.zeruj_wszystko(katalog)

    def test_zerowanie_po_kopii_zeruje_obie_bazy_i_kasuje_wybor_rozgrywek(self):
        katalog, _ = zerowanie.kopia(self.root / 'kopia')
        with patch.object(zerowanie, 'port_zajety', return_value=False):
            raporty = zerowanie.zeruj_wszystko(katalog)
        for m in zerowanie.MODULES:
            self.assertEqual(raporty[m]['po']['games'], 0)
            con = sqlite3.connect(self.root / 'modules' / m / 'instance' / 'database.db')
            self.assertEqual(con.execute('select count(*) from banners').fetchone()[0], 1)
            con.close()
            self.assertFalse((self.root / 'modules' / m / 'instance' / 'wp_rozgrywki.json').exists())
            self.assertTrue((katalog / m / 'wp_rozgrywki.json').exists())           # kopia zostaje

    def test_zerowanie_wp_odtwarza_baze_z_szablonu_ale_tylko_gdy_jest_kopia_i_port_wolny(self):
        katalog, _ = zerowanie.kopia(self.root / 'kopia')
        with patch.object(zerowanie, 'port_zajety', return_value=True):
            with self.assertRaises(SystemExit):
                zerowanie.zeruj_wp(katalog)
        with patch.object(zerowanie, 'port_zajety', return_value=False), patch.object(zerowanie.subprocess, 'run') as run:
            run.return_value.returncode = 0
            wynik = zerowanie.zeruj_wp(katalog)
        self.assertEqual(wynik['garbarnia']['baza'], 'p8092')
        baza = self.root / 'wp-local' / 'databases' / 'p8092'
        self.assertEqual((baza / '.ht.sqlite').read_bytes(), b'szablon')
        self.assertTrue((baza / '.htaccess').exists())
        self.assertEqual((katalog / 'wp' / 'p8092' / '.ht.sqlite').read_bytes(), b'baza 8092')   # kopia nienaruszona


if __name__ == '__main__':
    unittest.main()
