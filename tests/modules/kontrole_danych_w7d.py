"""W7d, krok 2: kontrole danych po pierwszym pobraniu z WP do bazy roboczej modułu (TYLKO ODCZYT bazy).

    python tests/modules/kontrole_danych_w7d.py <futsal_nalf|garbarnia> [ścieżka do pliku bazy]

Domyślnie sprawdza modules/<moduł>/instance/database.db otwartą w trybie tylko do odczytu. Sprawdza: integralność i klucze obce, liczności,
nazwy 14-znakowe i skróty, unikalność skrótów w lidze, istnienie plików logo na dysku, powiązania z WP (id źródła), spójność meczów
(drużyny należą do ligi, wynik zgodny ze statusem), numery rund i nazwy rund w pucharze, zawodników bez drużyny."""
import collections
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')

module = sys.argv[1] if len(sys.argv) > 1 else 'futsal_nalf'
db_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / 'modules' / module / 'instance' / 'database.db'
c = sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True)
wyniki = []


def sprawdz(nazwa, ok, szczegoly=''):
    wyniki.append(ok)
    print(f'{"OK   " if ok else "BŁĄD"} {nazwa}{(" — " + str(szczegoly)) if szczegoly != "" else ""}')


def q(sql, *a):
    return c.execute(sql, a).fetchall()


def n(tabela):
    return q(f'select count(*) from {tabela}')[0][0]




def _wczytaj_nazwe_rundy():
    """Funkcja round_name modułu, wczytana z kodu źródłowego (import pakietu core w tym skrypcie kończy się cyklem importów)."""
    import ast
    zrodlo = (REPO / 'modules' / 'core' / 'utils' / 'socketio_events_utils.py').read_text(encoding='utf-8')
    wezel = next(w for w in ast.parse(zrodlo).body if isinstance(w, ast.FunctionDef) and w.name == '_round_nr_to_round_name')
    ns = {}
    exec(compile(ast.Module(body=[wezel], type_ignores=[]), 'socketio_events_utils', 'exec'), ns)
    return ns['_round_nr_to_round_name']


_round_nr_to_round_name = _wczytaj_nazwe_rundy()

print(f'== Kontrole danych: {module} ({db_path})')
sprawdz('integralność bazy', q('pragma integrity_check')[0][0] == 'ok')
sprawdz('klucze obce', q('pragma foreign_key_check') == [])
print('liczności:', {t: n(t) for t in ('seasons', 'leagues', 'teams', 'players', 'games', 'league_teams', 'game_players', 'game_events', 'broadcast_sessions')})
sprawdz('brak wpisów składów, zdarzeń i sesji (baza po pobraniu, przed transmisją)', n('game_players') == 0 and n('game_events') == 0 and n('broadcast_sessions') == 0)

# drużyny
dr = q('select id, name, name_14, short_name, logo_path from teams')
sprawdz('nazwy 14-znakowe: niepuste i najwyżej 14 znaków', all(r[2] and len(r[2]) <= 14 for r in dr), [r[1] for r in dr if not (r[2] and len(r[2]) <= 14)])
sprawdz('skróty: niepuste i najwyżej 3 znaki', all(r[3] and len(r[3]) <= 3 for r in dr), [r[1] for r in dr if not (r[3] and len(r[3]) <= 3)])
for liga_id, liga in q('select id, name from leagues'):
    skroty = collections.Counter(r[0] for r in q('select t.short_name from teams t join league_teams lt on lt.team_id=t.id where lt.league_id=?', liga_id))
    sprawdz(f'skróty drużyn w lidze „{liga}” są unikalne', all(v == 1 for v in skroty.values()), [k for k, v in skroty.items() if v > 1])
brak_pliku = []
domyslne = 0
for r in dr:
    sciezka = (r[4] or '').lstrip('/')
    if not sciezka or not (REPO / 'modules' / sciezka).is_file():
        brak_pliku.append((r[1], r[4]))
    elif sciezka.endswith('default.png'):
        domyslne += 1
sprawdz('pliki logo wszystkich drużyn istnieją na dysku (modules/<logo_path>)', not brak_pliku, brak_pliku[:5])
print(f'      (drużyn z logo domyślnym default.png: {domyslne} z {len(dr)})')
sprawdz('logo_path bez początkowego ukośnika (postać kanoniczna)', all(not (r[4] or '').startswith('/') for r in dr))
sprawdz('nazwy drużyn unikalne', len({r[1] for r in dr}) == len(dr))

# powiązania z WP
sc = q("select id from scrapers where folder='wp'")
sprawdz('źródło „wp” w tabeli scrapers', len(sc) == 1)
if sc:
    sid = sc[0][0]
    for tab, kol, glowna in (('team_foreign_ids', 'team_id', 'teams'), ('player_foreign_ids', 'player_id', 'players'), ('game_foreign_ids', 'game_id', 'games'),
                             ('league_foreign_ids', 'league_id', 'leagues'), ('season_foreign_ids', 'season_id', 'seasons')):
        z = q(f'select count(*) from {glowna} where id not in (select {kol} from {tab} where scraper_id=?)', sid)[0][0]
        sprawdz(f'każdy rekord „{glowna}” ma powiązanie z WP', z == 0, f'bez powiązania: {z}')

# zawodnicy
sprawdz('zawodnicy: imię i nazwisko niepuste', q("select count(*) from players where trim(first_name)='' or trim(last_name)=''")[0][0] == 0)
sprawdz('zawodnicy: każdy ma drużynę (po pobraniu pary)', q('select count(*) from players where team_id is null')[0][0] == 0)
sprawdz('zawodnicy: brak duplikatów (ta sama osoba i drużyna)', q('select count(*) from (select last_name, first_name, team_id from players group by 1,2,3 having count(*)>1)')[0][0] == 0)
rozm = q('select t.short_name, count(p.id) from teams t left join players p on p.team_id=t.id group by t.id order by 2')
print(f'      (zawodników w drużynie: min {rozm[0][1]} [{rozm[0][0]}], max {rozm[-1][1]} [{rozm[-1][0]}])')

# mecze
sprawdz('mecze: gospodarz i gość to różne drużyny', q('select count(*) from games where home_team_id=away_team_id')[0][0] == 0)
sprawdz('mecze: obie drużyny należą do ligi meczu',
        q('select count(*) from games g where not exists (select 1 from league_teams lt where lt.league_id=g.league_id and lt.team_id=g.home_team_id) '
          'or not exists (select 1 from league_teams lt where lt.league_id=g.league_id and lt.team_id=g.away_team_id)')[0][0] == 0)
sprawdz('mecze: zakończony ma wynik, nierozpoczęty go nie ma',
        q('select count(*) from games where (status=2 and (home_team_goals is null or away_team_goals is null)) '
          'or (status=0 and (home_team_goals is not null or away_team_goals is not null))')[0][0] == 0)
sprawdz('mecze: stadion i data ustawione', q('select count(*) from games where stadium_id is null or date is null')[0][0] == 0)
print('      (mecze wg statusu 0/1/2:', dict(q('select status, count(*) from games group by status')), ')')
for liga_id, liga in q('select id, name from leagues'):
    rundy = dict(q('select round, count(*) from games where league_id=? group by round', liga_id))
    nazwy = {r: _round_nr_to_round_name(r, liga) for r in rundy}
    if 'puchar' in liga.lower():
        sprawdz(f'liga „{liga}”: rundy w zakresie 1-6, nazwy rund bez wyjątku', all(1 <= r <= 6 for r in rundy), nazwy)
    else:
        print(f'      liga „{liga}”: rundy {rundy}; round_name: {nazwy}')
        sprawdz(f'liga „{liga}”: round_name policzalny dla każdej rundy', all(isinstance(v, str) for v in nazwy.values()))
sprawdz('ligi: remis dozwolony tylko poza pucharem', all((a == 0) == ('puchar' in nm.lower()) for nm, a in q('select name, allows_draw from leagues')))

print(f'\nWYNIK ({module}): {"WSZYSTKIE KONTROLE ZALICZONE" if all(wyniki) else "SĄ BŁĘDY: " + str(wyniki.count(False))}')
sys.exit(0 if all(wyniki) else 1)
