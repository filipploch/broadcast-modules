"""Menedżer sesji transmisji (etap E1) — jedyne miejsce, które zmienia stan sesji i aktywnego meczu.

Zasady (docs/koncepcja-wp-sportspress.md, pkt 9):
  1. Aktualny mecz to aktywny mecz otwartej sesji. Brak otwartej sesji jest poprawnym stanem (current_game_id() == None).
  2. Sezon i rozgrywki nie są przechowywane osobno; wynikają z meczu.
  3. Otwarcie sesji, zmiana meczu i zamknięcie sesji to pojedyncze transakcje (jeden commit; przy błędzie rollback).
  6. Aktualny okres wynika ze statusów okresów meczu (select_period_for_game); nie jest nigdzie zapisany.

Sesja przechodzi w "na antenie" automatycznie, gdy OBS zgłosi start streamu albo nagrywania (on_obs_stream_started /
on_obs_recording_started), albo ręcznie (go_on_air). Zamknięcie sesji jest wyłącznie ręczne (close_session) i nigdy
nie następuje samo po zatrzymaniu streamu.
"""
import logging
from datetime import datetime

from core.extensions import db
from core.models.base_broadcast_session import get_broadcast_session_model, get_session_game_model

logger = logging.getLogger(__name__)


class SessionError(Exception):
    """Naruszenie zasad sesji (np. druga otwarta sesja, brak meczu). Message jest po polsku, do pokazania operatorowi."""


# ── Odczyt ───────────────────────────────────────────────────────────────────

def get_open_session():
    """Otwarta sesja (przygotowanie lub na antenie) albo None."""
    Session = get_broadcast_session_model()
    return Session.query.filter(Session.open_slot == 1).first()


def get_active_entry(session=None):
    """Pozycja aktywnego meczu otwartej sesji albo None."""
    session = session or get_open_session()
    if session is None:
        return None
    SessionGame = get_session_game_model()
    return SessionGame.query.filter_by(session_id=session.id, active_slot=1).first()


def current_session_id():
    s = get_open_session()
    return s.id if s else None


def current_game_id():
    e = get_active_entry()
    return e.game_id if e else None


def current_game():
    e = get_active_entry()
    return e.game if e else None


def current_season_id():
    """Sezon transmitowanego meczu (z ligi meczu) albo None. NIE jest to sezon wybrany do przeglądania list."""
    g = current_game()
    league = getattr(g, 'league', None) if g else None
    return league.season_id if league else None


def select_period_for_game(game_id):
    """Okres 'bieżący' dla meczu wyliczony ze statusów: trwający → ostatni zakończony → pierwszy nierozpoczęty → None.

    Zgodnie z dotychczasowym zachowaniem panelu: w przerwie między okresami (jeden zakończony, następny jeszcze
    nie ruszył) bieżący pozostaje okres zakończony, a nie następny nierozpoczęty. Dzięki temu miejsca używające
    'bieżącego okresu' (panel, sekwencje, zmiany w garbarni) w przerwie widzą to samo co przed E1; zdarzenia meczu
    nie trafiają do nierozpoczętego okresu (zdarzenia dodaje się tylko do okresu trwającego).
    """
    from core.models.base_period import get_period_model
    Period = get_period_model()
    periods = Period.query.filter_by(game_id=game_id).order_by(Period.period_order).all()
    for p in periods:
        if p.status == Period.STATUS_PENDING:
            return p
    finished = [p for p in periods if p.status == Period.STATUS_FINISHED]
    if finished:
        return finished[-1]
    for p in periods:
        if p.status == Period.STATUS_NOT_STARTED:
            return p
    return None


def select_period_for_control(game_id):
    """Okres wyświetlany na stronie sterowania zegarem ('/' = index): trwający → pierwszy nierozpoczęty → ostatni zakończony.

    To dawna reguła wyboru meczu i zapasowa reguła strony '/', używana wtedy, gdy wskaźnik okresu był pusty (np. po zakończeniu okresu
    przyciskiem 'Zakończ' w oknie wyboru części). W przerwie strona pokazuje więc NASTĘPNĄ, nierozpoczętą część z przyciskiem
    'Start'. Panel (select_period_for_game) w przerwie zostaje na ostatnio zakończonym okresie.
    """
    from core.models.base_period import get_period_model
    Period = get_period_model()
    periods = Period.query.filter_by(game_id=game_id).order_by(Period.period_order).all()
    for status in (Period.STATUS_PENDING, Period.STATUS_NOT_STARTED):
        for p in periods:
            if p.status == status:
                return p
    finished = [p for p in periods if p.status == Period.STATUS_FINISHED]
    return finished[-1] if finished else None


def current_period():
    gid = current_game_id()
    return select_period_for_game(gid) if gid else None


def current_period_id():
    p = current_period()
    return p.id if p else None


def current_shootout():
    """Konkurs rzutów karnych aktywnego meczu (rekord istnieje od startu konkursu do jego resetu) albo None."""
    g = current_game()
    return g.shootout if g is not None else None


# ── Zmiany stanu (każda = jedna transakcja) ──────────────────────────────────

def _commit():
    db.session.commit()


def _before_leaving(entry):
    """Zanim mecz przestanie być bieżący (zmiana meczu, następny mecz, zamknięcie sesji), moduł kończy jego sprawy w pluginach
    (pauza biegnącego zegara) i dopuszcza na chwilę odpowiedzi z jego kontekstu. Błąd tu nie przerywa zmiany meczu."""
    if entry is None:
        return
    try:
        from core.managers import get_timer_manager
        get_timer_manager().on_game_leaving(entry.session_id, entry.game_id)
    except Exception:
        logger.exception('Nie udało się zakończyć spraw meczu %s w pluginach przed zmianą meczu', entry.game_id)


def _release_active(entry, now):
    """Aktywny wpis przestaje być aktywny: zakończony, jeśli mecz się skończył, w przeciwnym razie wraca do kolejki."""
    from core.models.base_game import get_game_model
    Game = get_game_model()
    entry.active_slot = None
    if entry.game is not None and entry.game.status == Game.STATUS_FINISHED:
        entry.status = type(entry).STATUS_FINISHED
        entry.ended_at = now
    else:
        entry.status = type(entry).STATUS_QUEUED


def _next_position(session):
    SessionGame = get_session_game_model()
    last = db.session.query(db.func.max(SessionGame.position)).filter_by(session_id=session.id).scalar()
    return (last or 0) + 1


def open_session():
    """Otwiera nową sesję (przygotowanie). Błąd, jeśli jakaś sesja jest już otwarta."""
    Session = get_broadcast_session_model()
    if get_open_session() is not None:
        raise SessionError('Sesja transmisji jest już otwarta.')
    s = Session(status=Session.STATUS_PREPARATION, open_slot=1)
    db.session.add(s)
    try:
        _commit()
    except Exception:
        db.session.rollback()
        raise
    return s


def queue_game(game_id, session=None):
    """Dodaje mecz na koniec listy sesji (bez aktywacji). Zwraca pozycję."""
    from core.models.base_game import get_game_model
    session = session or get_open_session()
    if session is None:
        raise SessionError('Brak otwartej sesji transmisji.')
    if get_game_model().query.get(game_id) is None:
        raise SessionError('Nie znaleziono meczu.')
    SessionGame = get_session_game_model()
    entry = SessionGame.query.filter_by(session_id=session.id, game_id=game_id).first()
    if entry is None:
        entry = SessionGame(session_id=session.id, game_id=game_id, position=_next_position(session))
        db.session.add(entry)
        _commit()
    return entry


def activate_game(game_id, auto_open=True):
    """Ustawia mecz jako aktywny w otwartej sesji (jedna transakcja).

    Gdy nie ma otwartej sesji, a auto_open=True, otwiera ją (w stanie przygotowania). Poprzedni aktywny mecz wraca do
    kolejki (albo jest zakończony, jeśli się odbył). Zwraca pozycję aktywnego meczu.
    """
    from core.models.base_game import get_game_model
    Session = get_broadcast_session_model()
    SessionGame = get_session_game_model()
    if get_game_model().query.get(game_id) is None:
        raise SessionError('Nie znaleziono meczu.')
    try:
        session = get_open_session()
        if session is None:
            if not auto_open:
                raise SessionError('Brak otwartej sesji transmisji.')
            session = Session(status=Session.STATUS_PREPARATION, open_slot=1)
            db.session.add(session)
            db.session.flush()
        now = datetime.utcnow()
        previous = get_active_entry(session)
        if previous is not None and previous.game_id == game_id:
            return previous
        if previous is not None:
            _before_leaving(previous)
            _release_active(previous, now)
            db.session.flush()           # zwolnij active_slot zanim ustawimy nowy (UNIQUE)
        entry = SessionGame.query.filter_by(session_id=session.id, game_id=game_id).first()
        if entry is None:
            entry = SessionGame(session_id=session.id, game_id=game_id, position=_next_position(session))
            db.session.add(entry)
        entry.status = SessionGame.STATUS_ACTIVE
        entry.active_slot = 1
        entry.started_at = entry.started_at or now
        entry.ended_at = None
        _commit()
        return entry
    except Exception:
        db.session.rollback()
        raise


def next_game():
    """Kończy aktywny mecz i aktywuje następny z kolejki (jawna akcja 'następny mecz'; stream trwa dalej).

    Zwraca nowy aktywny wpis albo None, gdy kolejka jest pusta (wtedy sesja zostaje otwarta bez aktywnego meczu).
    """
    session = get_open_session()
    if session is None:
        raise SessionError('Brak otwartej sesji transmisji.')
    SessionGame = get_session_game_model()
    try:
        now = datetime.utcnow()
        current = get_active_entry(session)
        if current is not None:
            _before_leaving(current)
            current.active_slot = None
            current.status = SessionGame.STATUS_FINISHED
            current.ended_at = now
            db.session.flush()
        queued = (SessionGame.query.filter_by(session_id=session.id, status=SessionGame.STATUS_QUEUED)
                  .order_by(SessionGame.position).first())
        if queued is not None:
            queued.status = SessionGame.STATUS_ACTIVE
            queued.active_slot = 1
            queued.started_at = queued.started_at or now
        _commit()
        return queued
    except Exception:
        db.session.rollback()
        raise


def go_on_air():
    """Przejście w 'na antenie' (przycisk operatora lub zdarzenie OBS). Idempotentne; bez otwartej sesji nic nie robi."""
    Session = get_broadcast_session_model()
    session = get_open_session()
    if session is None or session.status == Session.STATUS_ON_AIR:
        return session
    session.status = Session.STATUS_ON_AIR
    session.started_at = datetime.utcnow()
    _commit()
    return session


def on_obs_stream_started():
    s = update_obs_state(streaming=True)
    return go_on_air() if s else None


def on_obs_recording_started():
    s = update_obs_state(recording=True)
    return go_on_air() if s else None


def update_obs_state(scene=None, recording=None, streaming=None):
    """Zapisuje w otwartej sesji stan OBS. Zatrzymanie streamu/nagrywania NIE zamyka sesji."""
    session = get_open_session()
    if session is None:
        return None
    if scene is not None:
        session.obs_scene = scene
    if recording is not None:
        session.obs_recording = bool(recording)
    if streaming is not None:
        session.obs_streaming = bool(streaming)
    _commit()
    return session


def close_session():
    """Ręczne zamknięcie sesji (jedyna droga zamknięcia). Aktywny mecz wraca do kolejki albo jest zakończony."""
    Session = get_broadcast_session_model()
    session = get_open_session()
    if session is None:
        raise SessionError('Brak otwartej sesji transmisji.')
    try:
        now = datetime.utcnow()
        active = get_active_entry(session)
        if active is not None:
            _before_leaving(active)
            _release_active(active, now)
        session.status = Session.STATUS_FINISHED
        session.open_slot = None
        session.ended_at = now
        _commit()
        return session
    except Exception:
        db.session.rollback()
        raise


def describe():
    """Stan sesji do API/interfejsu: dict albo {'open': False}."""
    s = get_open_session()
    if s is None:
        return {'open': False}
    e = get_active_entry(s)
    return {
        'open': True, 'session_id': s.id, 'status': s.status,
        'started_at': s.started_at.isoformat() if s.started_at else None,
        'game_id': e.game_id if e else None,
        'period_id': current_period_id(),
        'obs': {'scene': s.obs_scene, 'recording': s.obs_recording, 'streaming': s.obs_streaming},
        'queue': [{'game_id': x.game_id, 'position': x.position, 'status': x.status} for x in s.session_games],
    }
