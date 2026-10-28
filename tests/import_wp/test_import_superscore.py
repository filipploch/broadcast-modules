"""Etap I2: importer Garbarni z Superscore (tools/import_wp/superscore.py + wspólny zapis do WP).

Dane: tests/import_wp/dane/superscore_sezon.json to wycinek PRAWDZIWYCH odpowiedzi Superscore (sezon 2026/2027, 5. liga zachód): terminarz
(mecz zakończony z wynikiem do przerwy, nierozpoczęty, zakończony remisem, jeden zmieniony na „w toku”) i kadra jednej drużyny."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'import_wp'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importuj  # noqa: E402
import superscore  # noqa: E402
from atrapa_wp import AtrapaWp  # noqa: E402
from wp_rest import WpRest  # noqa: E402

FX = json.loads((Path(__file__).resolve().parent / 'dane' / 'superscore_sezon.json').read_text(encoding='utf-8'))
KONF = {'sezon': '33lvZK65l7ubf6BfFPjtl', 'liga': {'id': '0loc9tw7', 'nazwa': 'Hal-Mont Małopolska 5. Liga Zachód'}, 'nazwa_sezonu': 'Sezon 2026/2027',
        'nazwy': {'66r9558e': 'KS Chełmek'}}
ZAKONCZONY, NIEROZPOCZETY, W_TOKU, REMIS = FX['finished_id'], FX['notstarted_id'], FX['live_id'], FX['draw_id']
ORZEL = '2e2ert7e'
KADRA2 = 'leea26wi'          # druga drużyna z tym samym zawodnikiem w kadrze (test zawodnika w dwóch kadrach)


class AtrapaSuperscore:
    def __init__(self, fx=None, kadry=None):
        self.fx = copy.deepcopy(fx or FX['fixtures'])
        self.kadry = kadry if kadry is not None else {ORZEL: FX['squads'][ORZEL], KADRA2: FX['squad_dup']}
        self.zapytania = 0
        self.z_pamieci = 0
        self.wywolania = []

    def get(self, url, **params):
        self.zapytania += 1
        self.wywolania.append((url, params))
        if url == superscore.FIXTURES:
            return copy.deepcopy(self.fx)
        return copy.deepcopy(self.kadry.get(params['team-id'], {}))


def dane(api=None, **kw):
    return superscore.pobierz_sezon(api or AtrapaSuperscore(), KONF, log=lambda *a: None, **kw)


def utc(*czesci):
    return int(datetime(*czesci, tzinfo=timezone.utc).timestamp())


class CzasTests(unittest.TestCase):
    def test_czas_lokalny_pl_lato_zima_i_granice_zmiany_czasu(self):
        self.assertEqual(superscore.czas_lokalny_pl(utc(2026, 7, 15, 12)), '2026-07-15T14:00:00')       # lato +2
        self.assertEqual(superscore.czas_lokalny_pl(utc(2026, 1, 15, 12)), '2026-01-15T13:00:00')       # zima +1
        self.assertEqual(superscore.czas_lokalny_pl(utc(2026, 3, 29, 0, 59)), '2026-03-29T01:59:00')    # tuż przed zmianą na letni
        self.assertEqual(superscore.czas_lokalny_pl(utc(2026, 3, 29, 1, 0)), '2026-03-29T03:00:00')     # od 01:00 UTC +2
        self.assertEqual(superscore.czas_lokalny_pl(utc(2026, 10, 25, 0, 30)), '2026-10-25T02:30:00')   # jeszcze lato (+2)
        self.assertEqual(superscore.czas_lokalny_pl(utc(2026, 10, 25, 1, 30)), '2026-10-25T02:30:00')   # od 01:00 UTC zima (+1)


class NormalizacjaTests(unittest.TestCase):
    def test_mecz_zakonczony_ma_wynik_polowy_i_wynik_meczu(self):
        m = next(x for x in dane()['mecze'] if x['id'] == ZAKONCZONY)
        g, a = m['teams']
        self.assertEqual(m['results'][g], {'goals': '1', 'outcome': ['loss'], 'firsthalf': '0', 'secondhalf': '1'})
        self.assertEqual(m['results'][a], {'goals': '2', 'outcome': ['win'], 'firsthalf': '1', 'secondhalf': '1'})
        self.assertEqual((m['day'], m['format'], m['leagues'], m['seasons']), ('', 'league', ['0loc9tw7'], ['33lvZK65l7ubf6BfFPjtl']))
        self.assertRegex(m['date'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$')

    def test_remis_oznaczony_jako_remis_u_obu_druzyn(self):
        m = next(x for x in dane()['mecze'] if x['id'] == REMIS)
        self.assertEqual([r['outcome'] for r in m['results'].values()], [['draw'], ['draw']])

    def test_nierozpoczety_i_trwajacy_nie_maja_wyniku(self):
        mecze = {x['id']: x for x in dane()['mecze']}
        self.assertEqual(mecze[NIEROZPOCZETY]['results'], {})
        self.assertEqual(mecze[W_TOKU]['results'], {})

    def test_druzyny_hash_jako_id_skrot_i_poprawione_nazwy(self):
        d = dane()
        nazwy = {t['id']: t for t in d['druzyny']}
        self.assertEqual(nazwy['66r9558e']['name'], 'KS Chełmek')                  # nazwa z pliku konfiguracji (Superscore: bez polskich znaków)
        self.assertEqual(nazwy[ORZEL]['name'], 'Orzel Myslenice')                   # bez nadpisania: nazwa ze źródła
        self.assertEqual(nazwy[ORZEL]['abbreviation'], 'ORZ')
        self.assertEqual(nazwy[ORZEL]['slug'], 'orzel-myslenice')
        self.assertEqual(len(d['druzyny']), len(FX['druzyny']))

    def test_zawodnik_nazwisko_imie_numer_i_brak_numeru(self):
        d = dane()
        gracze = {p['name']: p for p in d['zawodnicy']}
        self.assertIn('Bargieł Bartosz', gracze)                                   # "Nazwisko, Imię" -> "Nazwisko Imię"
        self.assertEqual(gracze['Bargieł Bartosz']['number'], 9)                   # numer z drugiej kadry nie nadpisuje pierwszego wpisu
        self.assertCountEqual(gracze['Bargieł Bartosz']['teams'], [ORZEL, KADRA2])  # ten sam zawodnik w dwóch kadrach: jeden rekord
        self.assertEqual(len(d['zawodnicy']), 3)
        self.assertCountEqual(gracze['Bargieł Bartosz']['current_teams'], [ORZEL, KADRA2])      # skład drużyny = aktualna kadra; dawnych drużyn brak
        self.assertEqual(gracze['Bargieł Bartosz']['past_teams'], [])
        self.assertTrue(next(p for p in d['zawodnicy'] if p['name'].startswith('Biela'))['id'].startswith('fake:player:'))   # bez seo_id też importowany
        self.assertIsNone(next(p for p in d['zawodnicy'] if p['name'].startswith('Br'))['number'])                          # pusty numer koszulki

    def test_bez_zawodnikow_nie_pyta_o_kadry(self):
        api = AtrapaSuperscore()
        d = dane(api, z_zawodnikami=False)
        self.assertEqual(d['zawodnicy'], [])
        self.assertTrue(all(w[0] == superscore.FIXTURES for w in api.wywolania))

    def test_pusty_terminarz_to_czytelny_blad_a_next_page_to_uwaga(self):
        puste = AtrapaSuperscore({'next_page': None, 'events': []})
        with self.assertRaises(SystemExit) as cm:
            dane(puste)
        self.assertIn('nie zwróciło meczów', str(cm.exception))
        fx = copy.deepcopy(FX['fixtures'])
        fx['next_page'] = 'cos'
        self.assertTrue(any('next_page' in u for u in dane(AtrapaSuperscore(fx))['uwagi']))


class ImportDoWpTests(unittest.TestCase):
    def setUp(self):
        self.a = AtrapaWp()
        self.addCleanup(self.a.zamknij)
        self.wp = WpRest(f'http://127.0.0.1:{self.a.port}', 'operator', 'tajne')

    def _importuj(self, d=None, **kw):
        return importuj.importuj_zrodlo(self.wp, 'superscore', d or dane(), log=lambda *a: None, **kw)

    def test_pierwszy_import_tworzy_rozgrywki_druzyny_zawodnikow_i_mecze(self):
        imp = self._importuj()
        self.assertEqual((len(self.a.dane['leagues']), len(self.a.dane['seasons']), len(self.a.dane['teams']), len(self.a.dane['players']),
                          len(self.a.dane['events'])), (1, 1, len(FX['druzyny']), 3, 4))
        sezon = next(iter(self.a.dane['seasons'].values()))
        self.assertEqual((sezon['name'], sezon['slug']), ('Sezon 2026/2027', 'superscore-s33lvzk65l7ubf6bffpjtl'))     # slug małymi literami
        liga = next(iter(self.a.dane['leagues'].values()))
        self.assertEqual((liga['name'], liga['slug']), ('Hal-Mont Małopolska 5. Liga Zachód', 'superscore-l0loc9tw7'))
        mecz = self.a.po_zrodle('events', ZAKONCZONY)
        g, a = (imp.id_wp['druzyny'][t] for t in dane()['mecze'][0]['teams'])
        self.assertEqual(mecz['teams'], [g, a])
        self.assertEqual(mecz['results'][str(a)]['outcome'], ['win'])
        self.assertEqual(mecz['meta']['bm_source'], 'superscore')
        self.assertNotIn('results', self.a.po_zrodle('events', NIEROZPOCZETY))
        self.assertNotIn('results', self.a.po_zrodle('events', W_TOKU))

    def test_drugi_import_niczego_nie_dubluje_ani_nie_wysyla_w_tym_kategorii_z_wielkimi_literami(self):
        self._importuj()
        liczba = {k: len(v) for k, v in self.a.dane.items()}
        self.a.wyzeruj_zapytania()
        imp = self._importuj()
        self.assertEqual({k: len(v) for k, v in self.a.dane.items()}, liczba)
        self.assertEqual(self.a.posty(), [])
        self.assertEqual((imp.liczniki['sezon'].bez_zmian, imp.liczniki['ligi'].bez_zmian), (1, 1))
        for rodzaj in ('druzyny', 'zawodnicy', 'mecze'):
            l = imp.liczniki[rodzaj]
            self.assertEqual((l.nowe, l.zmienione, l.bledy), (0, 0, 0), rodzaj)

    def test_zmiana_wyniku_w_zrodle_aktualizuje_tylko_ten_mecz(self):
        self._importuj()
        fx = copy.deepcopy(FX['fixtures'])
        e = next(x for x in fx['events'] if x['id'] == ZAKONCZONY)
        next(s for s in e['scores'] if s['type'] == 0)['team1'] = 5
        self.a.wyzeruj_zapytania()
        imp = self._importuj(dane(AtrapaSuperscore(fx)))
        self.assertEqual((imp.liczniki['mecze'].zmienione, imp.liczniki['mecze'].bez_zmian), (1, 3))
        self.assertEqual(len(self.a.posty()), 1)
        mecz = self.a.po_zrodle('events', ZAKONCZONY)
        self.assertEqual(self.a.wyczyszczone, [mecz['id']])
        self.assertEqual(sorted(v['goals'] for v in mecz['results'].values()), ['2', '5'])

    def test_mecz_zakonczony_po_rozpoczeciu_dostaje_wynik_przy_kolejnym_imporcie(self):
        self._importuj()
        fx = copy.deepcopy(FX['fixtures'])
        e = next(x for x in fx['events'] if x['id'] == W_TOKU)
        e['match_state'] = 2
        imp = self._importuj(dane(AtrapaSuperscore(fx)))
        self.assertEqual(imp.liczniki['mecze'].zmienione, 1)
        self.assertIn('results', self.a.po_zrodle('events', W_TOKU))

    def test_zmiana_identyfikatora_zawodnika_w_zrodle_jest_zgloszona_jako_mozliwy_duplikat(self):
        imp = self._importuj()
        self.assertEqual(imp.liczniki['zawodnicy'].duplikaty, [])                       # zwykły import: bez fałszywych alarmów
        kadry = copy.deepcopy(self.AtrapaKadry())
        for wpis in kadry[ORZEL]['other']:
            if wpis['player']['name'].startswith('Biela'):
                wpis['player']['id'] = 'fake:player:00000000-nowy-identyfikator'      # Superscore zmieniło identyfikator
        imp = self._importuj(dane(AtrapaSuperscore(kadry=kadry)))
        l = imp.liczniki['zawodnicy']
        self.assertEqual((l.nowe, l.bez_zmian), (1, 2))
        self.assertEqual(len(l.duplikaty), 1)
        self.assertIn('Biela Wiktor', l.duplikaty[0])
        self.assertIn('00000000-nowy-identyfikator', l.duplikaty[0])
        self.assertIn('możliwy duplikat zawodnika', importuj.raport(imp, False))
        self.assertEqual(len(self.a.dane['players']), 4)                                 # stary rekord nie jest usuwany

    def test_ten_sam_zawodnik_w_innej_druzynie_nie_jest_duplikatem(self):
        self._importuj()
        kadry = copy.deepcopy(self.AtrapaKadry())
        kadry[KADRA2] = {'other': [{'shirt_number': '1', 'player': {'id': 'fake:player:inny', 'name': 'Biela, Wiktor'}}]}      # ta sama nazwa, inna drużyna
        kadry[ORZEL]['other'] = [w for w in kadry[ORZEL]['other'] if not w['player']['name'].startswith('Biela')]
        imp = self._importuj(dane(AtrapaSuperscore(kadry=kadry)))
        self.assertEqual(imp.liczniki['zawodnicy'].duplikaty, [])

    def test_zawodnik_w_dwoch_kadrach_ma_dwie_aktualne_druzyny_w_wp_i_w_raporcie(self):
        imp = self._importuj()
        rekord = next(o for o in self.a.dane['players'].values() if o['title'].startswith('Bargie'))
        self.assertEqual(sorted(rekord['current_teams']), sorted([imp.id_wp['druzyny'][ORZEL], imp.id_wp['druzyny'][KADRA2]]))
        self.assertEqual(rekord['past_teams'], [])
        self.assertEqual(sorted(rekord['teams']), sorted(rekord['current_teams']))               # wspólna lista wysłana razem z aktualnymi
        self.assertEqual(len(imp.przynaleznosc['kilka']), 1)
        self.assertIn('Bargieł Bartosz', imp.przynaleznosc['kilka'][0])
        self.assertIn('KILKA AKTUALNYCH DRUŻYN (1)', importuj.raport(imp, False))

    @staticmethod
    def AtrapaKadry():
        return {ORZEL: FX['squads'][ORZEL], KADRA2: FX['squad_dup']}

    def test_rekordy_nalf_nie_sa_dopasowywane_do_rekordow_superscore(self):
        self._importuj()
        for o in self.a.dane['teams'].values():
            o['meta']['bm_source'] = 'nalf'
        imp = self._importuj()
        self.assertEqual(imp.liczniki['druzyny'].nowe, len(FX['druzyny']))


if __name__ == '__main__':
    unittest.main()
