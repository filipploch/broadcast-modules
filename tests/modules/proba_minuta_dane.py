"""Próba ręczna reguły minuty (krok B2): do KOPII bazy (modules/<moduł>/instance/database-proba.db) dodaje dla jednego meczu okresy i zdarzenia
o dokładnych czasach zegara, żeby po wybraniu meczu można je kolejno pokazać na nakładce i porównać minutę z oczekiwaną (tabela jest wypisywana i zapisywana).

    python tests/modules/proba_minuta_dane.py <futsal_nalf|garbarnia> [id meczu]

Nie dotyka bazy roboczej (modules/<moduł>/instance/database.db): pracuje wyłącznie na database-proba.db, którą wcześniej przygotował prepare_dry_run.py.
Domyślny mecz: NALF Brotherm – MK Team (id 15), Garbarnia MKS Trzebinia – Świt Krzeszowice (id 24)."""
import json
import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')
MODULE = sys.argv[1] if len(sys.argv) > 1 else 'futsal_nalf'
GAME_ID = int(sys.argv[2]) if len(sys.argv) > 2 else {'futsal_nalf': 15, 'garbarnia': 24}[MODULE]
DB = REPO / 'modules' / MODULE / 'instance' / 'database-proba.db'
if not DB.exists():
    sys.exit(f'Brak {DB}: najpierw tests/modules/prepare_dry_run.py {MODULE}')
os.environ['BM_TEST_DATABASE_URL'] = 'sqlite:///' + DB.as_posix()
sys.path[:0] = [str(REPO / 'modules' / MODULE), str(REPO / 'modules'), str(pathlib.Path(__file__).resolve().parent)]
os.chdir(REPO / 'modules' / MODULE)

POLOWA_S = {'futsal_nalf': 20 * 60, 'garbarnia': 45 * 60}[MODULE]
OVERLAY = {'futsal_nalf': 'futsal-nalf', 'garbarnia': 'garbarnia'}[MODULE]


def mmss(t):
    return f'{t // 60}:{t % 60:02d}'


def oczekiwane(t, S, E, doliczony):
    """Reguła minuty (docs/regula-minuty.md), niezależna od kodu nakładek."""
    if t <= S:
        return f"{S // 60 + 1}'"
    if t <= E or not doliczony:
        return f"{-(-t // 60)}'"
    return f"{E // 60}+{-(-(t - E) // 60)}'"


# (okres 1/2, czas względem początku okresu w sekundach): wybrane przypadki graniczne
L = POLOWA_S
PRZYPADKI = [(1, 0), (1, 1), (1, 59), (1, 60), (1, 61), (1, L - 30), (1, L - 1), (1, L)]
if MODULE == 'garbarnia':
    PRZYPADKI += [(1, L + 5), (1, L + 60), (1, L + 61)]                      # doliczony czas
PRZYPADKI += [(2, 0), (2, 1), (2, 60), (2, 61), (2, L - 30), (2, L)]
if MODULE == 'garbarnia':
    PRZYPADKI += [(2, L + 5), (2, L + 61)]

from app import create_app  # noqa: E402
app = create_app('testing')
with app.app_context():
    from core.extensions import db
    from core.managers.period_manager import PeriodManager
    from app.models import Event, Game, GameEvent, Period, Player
    game = db.session.get(Game, GAME_ID)
    if game is None:
        sys.exit(f'W kopii bazy nie ma meczu {GAME_ID}')
    if Period.query.filter_by(game_id=GAME_ID).count() == 0:
        PeriodManager().create_default_periods(game_id=GAME_ID)
    p1, p2 = Period.query.filter_by(game_id=GAME_ID).order_by(Period.period_order).all()[:2]
    p1.initial_time, p1.limit = 0, L * 1000
    p2.initial_time, p2.limit = L * 1000, L * 1000
    ev = Event.query.filter_by(name='Bramka').first() or Event.query.first()
    zawodnik = Player.query.filter_by(team_id=game.home_team_id).order_by(Player.last_name).first()      # bez zawodnika panel nie daje przycisku „pokaż na nakładce”
    stare = GameEvent.query.filter_by(game_id=GAME_ID, comment='PROBA MINUTY').all()
    for s in stare:
        db.session.delete(s)
    db.session.flush()
    wiersze = []
    for okres, rel in PRZYPADKI:
        p = p1 if okres == 1 else p2
        S, E = p.initial_time // 1000, (p.initial_time + p.limit) // 1000
        t = S + rel
        db.session.add(GameEvent(game_id=GAME_ID, event_id=ev.id, period_id=p.id, team_id=game.home_team_id, player_id=zawodnik.id if zawodnik else None,
                                 event_place='H5', game_time=t, comment='PROBA MINUTY', home_team_goals=0, away_team_goals=0))     # H5: środek boiska (A-O, 1-9)
        wiersze.append((okres, mmss(t), oczekiwane(t, S, E, MODULE == 'garbarnia')))
    db.session.commit()
    tekst = [f'Próba minuty, moduł {MODULE}, mecz {GAME_ID} ({game.home_team.name} – {game.away_team.name}); okresy po {L // 60} min; zdarzenia typu „{ev.name}” zawodnika {zawodnik.last_name if zawodnik else "(brak)"}, komentarz „PROBA MINUTY”',
             'okres | czas na zegarze | oczekiwana minuta na nakładce']
    tekst += [f'  {o}. połowa | {c:>7} | {m}' for o, c, m in wiersze]
    wyjscie = '\n'.join(tekst)
    print(wyjscie)
    cel = REPO / 'wp-local' / 'probe-b-minuta' / f'oczekiwane-minuty-{MODULE}.txt'
    cel.parent.mkdir(parents=True, exist_ok=True)
    cel.write_text(wyjscie, encoding='utf-8')
    print(f'\n(zapisano: {cel})')
