"""
game_scraper_mzpn.py
Scraper terminarza/wyników z malopolskizpn.pl

URL: https://malopolskizpn.pl/rozgrywki/2025-2026/seniorzy/iv_liga/?view=schedule

Struktura HTML:
    <div class="mzpn-schedule">
        <div class="mzpn-round-title">Kolejka 1</div>
        <div class="mzpn-match">
            <div class="dt">
                <span class="d">9.08.2025</span>
                <span class="t"> 11:00</span>
            </div>
            <div class="teams">
                <span class="h">GARBARNIA KRAKÓW</span>
                <span class="s">2:0 (1:0)</span>   ← pusty = brak wyniku
                <span class="g">OKOCIMSKI KLUB...</span>
            </div>
        </div>
        ...
        <div class="mzpn-round-title">Kolejka 2</div>
        ...
    </div>

Dopasowanie nazw drużyn: porównanie case-insensitive z normalizacją białych znaków.
"""
import re
import logging
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SCHEDULE_URL = 'https://malopolskizpn.pl/rozgrywki/2025-2026/seniorzy/iv_liga/?view=schedule'
_SCORE_RE = re.compile(r'(\d+):(\d+)\s*\((\d+):(\d+)\)')
_DATE_RE  = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')
_TIME_RE  = re.compile(r'(\d{1,2}):(\d{2})')


# ── Pobieranie HTML ──────────────────────────────────────────────────────────

def fetch_schedule_html(url: str = SCHEDULE_URL, timeout: int = 15) -> str:
    """Pobierz HTML strony z terminarzem."""
    resp = requests.get(url, timeout=timeout, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; broadcast-scraper/1.0)'
    })
    resp.raise_for_status()
    return resp.text


def load_schedule_html(path: str | Path) -> str:
    """Wczytaj HTML z pliku lokalnego (do testów)."""
    return Path(path).read_text(encoding='utf-8')


# ── Parsowanie HTML ──────────────────────────────────────────────────────────

def parse_score(score_text: str) -> dict:
    """
    Parsuj wynik z formatu '2:0 (1:0)'.

    Returns:
        {
            'home_goals':    int | None,
            'away_goals':    int | None,
            'home_ht_goals': int | None,   # do przerwy
            'away_ht_goals': int | None,
            'is_finished':   bool,
        }
    """
    empty = {
        'home_goals':    None,
        'away_goals':    None,
        'home_ht_goals': None,
        'away_ht_goals': None,
        'is_finished':   False,
    }
    if not score_text or not score_text.strip():
        return empty
    m = _SCORE_RE.search(score_text)
    if not m:
        return empty
    return {
        'home_goals':    int(m.group(1)),
        'away_goals':    int(m.group(2)),
        'home_ht_goals': int(m.group(3)),
        'away_ht_goals': int(m.group(4)),
        'is_finished':   True,
    }


def parse_datetime(date_text: str, time_text: str) -> Optional[datetime]:
    """
    Połącz datę '9.08.2025' i godzinę '11:00' w obiekt datetime.
    Zwraca None jeśli parsowanie się nie uda.
    """
    dm = _DATE_RE.search(date_text or '')
    tm = _TIME_RE.search(time_text or '')
    if not dm:
        return None
    day, month, year = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
    hour   = int(tm.group(1)) if tm else 0
    minute = int(tm.group(2)) if tm else 0
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def parse_schedule(html: str) -> list[dict]:
    """
    Parsuj HTML terminarza, zwróć listę meczów z numerem kolejki.

    Returns:
        [
            {
                'round':         int,
                'date':          datetime | None,
                'home_name_raw': str,          # oryginalna nazwa z WWW (wielkie litery)
                'away_name_raw': str,
                'home_goals':    int | None,
                'away_goals':    int | None,
                'home_ht_goals': int | None,
                'away_ht_goals': int | None,
                'is_finished':   bool,
            },
            ...
        ]
    """
    soup     = BeautifulSoup(html, 'html.parser')
    schedule = soup.select_one('.mzpn-schedule')
    if not schedule:
        logger.error("Nie znaleziono elementu .mzpn-schedule")
        return []

    games        = []
    current_round = None

    for element in schedule.children:
        if not element.name:
            continue

        classes = element.get('class') or []

        # ── Nowa kolejka ──────────────────────────────────────────────────
        if 'mzpn-round-title' in classes:
            text = element.text.strip()          # "Kolejka 1"
            m = re.search(r'\d+', text)
            current_round = int(m.group()) if m else None
            logger.debug(f"Kolejka {current_round}")
            continue

        # ── Mecz ──────────────────────────────────────────────────────────
        if 'mzpn-match' not in classes:
            continue
        if current_round is None:
            logger.warning("Mecz bez przypisanej kolejki — pomijam")
            continue

        date_el  = element.select_one('.d')
        time_el  = element.select_one('.t')
        home_el  = element.select_one('.h')
        away_el  = element.select_one('.g')
        score_el = element.select_one('.s')

        date_text  = date_el.text.strip()   if date_el  else ''
        time_text  = time_el.text.strip()   if time_el  else ''
        home_raw   = home_el.text.strip()   if home_el  else ''
        away_raw   = away_el.text.strip()   if away_el  else ''
        score_text = score_el.text.strip()  if score_el else ''

        # Normalizuj białe znaki (strona używa &nbsp;)
        home_raw = re.sub(r'\s+', ' ', home_raw)
        away_raw = re.sub(r'\s+', ' ', away_raw)

        score = parse_score(score_text)
        dt    = parse_datetime(date_text, time_text)

        games.append({
            'round':         current_round,
            'date':          dt,
            'home_name_raw': home_raw,
            'away_name_raw': away_raw,
            **score,
        })

    logger.info(f"Sparsowano {len(games)} meczów w {current_round or 0} kolejkach")
    return games


# ── Dopasowanie drużyn ───────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """Normalizuj nazwę do porównania: małe litery, jeden spacja między słowami."""
    return re.sub(r'\s+', ' ', name.lower().strip())


def build_team_lookup(teams: list) -> dict[str, object]:
    """
    Zbuduj słownik {normalized_name -> team_object} dla szybkiego dopasowania.

    Args:
        teams: lista obiektów Team z atrybutami .name

    Returns:
        Słownik gotowy do użycia w match_team()
    """
    return {_normalize(t.name): t for t in teams}


def match_team(raw_name: str, lookup: dict) -> Optional[object]:
    """
    Dopasuj surową nazwę z WWW do obiektu Team ze słownika.

    Strategia:
    1. Dokładne dopasowanie (po normalizacji)
    2. Brak dopasowania → None (loguj ostrzeżenie)

    Args:
        raw_name: nazwa drużyny z WWW (np. 'GARBARNIA KRAKÓW')
        lookup:   słownik z build_team_lookup()

    Returns:
        Obiekt Team lub None
    """
    key  = _normalize(raw_name)
    team = lookup.get(key)
    if team is None:
        logger.warning(f"Nie dopasowano drużyny: '{raw_name}' (normalized: '{key}')")
    return team


# ── Tworzenie rekordów w bazie ────────────────────────────────────────────────

def import_schedule(
    html: str,
    league_id: int,
    teams: list,
    stadium_id: int = 1,
    db_session=None,
    game_model=None,
    period_model=None,
) -> dict:
    """
    Zaimportuj terminarz/wyniki do bazy danych.

    Dla każdego meczu:
    - Tworzy rekord Game (lub aktualizuje jeśli już istnieje — match po league_id + round + team_ids)
    - Tworzy 2 okresy (1. i 2. połowa) z bramkami z przerwy / końca meczu
    - Ustawia status: STATUS_FINISHED jeśli wynik, STATUS_NOT_STARTED jeśli brak

    Args:
        html:         Sparsowany HTML (string)
        league_id:    ID ligi w bazie
        teams:        Lista obiektów Team z tej ligi/sezonu
        stadium_id:   Domyślny stadion (1 jeśli nieznany)
        db_session:   SQLAlchemy session (db.session)
        game_model:   Klasa Game (z get_game_model())
        period_model: Klasa Period (z get_period_model())

    Returns:
        {'created': int, 'updated': int, 'skipped': int}
    """
    from core.extensions import db as _db

    if db_session is None:
        db_session = _db.session
    if game_model is None:
        from core.models.base_game import get_game_model
        game_model = get_game_model()
    if period_model is None:
        from core.models.base_period import get_period_model
        period_model = get_period_model()

    games_data = parse_schedule(html)
    lookup     = build_team_lookup(teams)
    stats      = {'created': 0, 'updated': 0, 'skipped': 0}

    for gd in games_data:
        home_team = match_team(gd['home_name_raw'], lookup)
        away_team = match_team(gd['away_name_raw'], lookup)

        if not home_team or not away_team:
            logger.warning(
                f"Pominięto mecz kolejka={gd['round']} "
                f"'{gd['home_name_raw']}' vs '{gd['away_name_raw']}' — brak drużyny w bazie"
            )
            stats['skipped'] += 1
            continue

        is_finished  = gd['is_finished']
        home_goals   = gd['home_goals']
        away_goals   = gd['away_goals']
        home_ht      = gd['home_ht_goals']   # bramki 1. połowy dla gospodarzy
        away_ht      = gd['away_ht_goals']

        # Bramki 2. połowy = końcowe - pierwsza połowa
        home_2h = (home_goals - home_ht) if is_finished else 0
        away_2h = (away_goals - away_ht) if is_finished else 0

        # Status meczu
        status = (game_model.STATUS_FINISHED
                  if is_finished
                  else game_model.STATUS_NOT_STARTED)

        # ── Szukaj istniejącego meczu (nie duplikuj) ──────────────────────
        existing = game_model.query.filter_by(
            league_id=league_id,
            round=gd['round'],
            home_team_id=home_team.id,
            away_team_id=away_team.id,
        ).first()

        if existing:
            # Aktualizuj tylko wynik i status
            existing.status          = status
            existing.home_team_goals = home_goals
            existing.away_team_goals = away_goals
            existing.date            = gd['date'] or existing.date
            existing.updated_at      = datetime.utcnow()
            game = existing
            stats['updated'] += 1
        else:
            game = game_model(
                league_id    = league_id,
                round        = gd['round'],
                group_nr     = 1,
                home_team_id = home_team.id,
                away_team_id = away_team.id,
                stadium_id   = stadium_id,
                date         = gd['date'],
                status       = status,
                home_team_goals = home_goals,
                away_team_goals = away_goals,
            )
            db_session.add(game)
            db_session.flush()   # potrzebne żeby game.id było dostępne przed commit
            stats['created'] += 1

        # ── Okresy (1. i 2. połowa) ───────────────────────────────────────
        _upsert_periods(
            game         = game,
            period_model = period_model,
            db_session   = db_session,
            home_ht      = home_ht  if is_finished else 0,
            away_ht      = away_ht  if is_finished else 0,
            home_2h      = home_2h,
            away_2h      = away_2h,
            is_finished  = is_finished,
        )

    db_session.commit()
    logger.info(
        f"Import zakończony: created={stats['created']} "
        f"updated={stats['updated']} skipped={stats['skipped']}"
    )
    return stats


def _upsert_periods(game, period_model, db_session,
                    home_ht, away_ht, home_2h, away_2h, is_finished):
    """
    Utwórz lub zaktualizuj dwa okresy dla meczu.
    """
    status_finished  = period_model.STATUS_FINISHED
    status_not_started = period_model.STATUS_NOT_STARTED

    periods_data = [
        {
            'period_order': 1,
            'description':  '1. połowa',
            'limit':        2700000,   # 45 minut w ms
            'initial_time': 0,
            'home_team_goals': home_ht,
            'away_team_goals': away_ht,
            'status': status_finished if is_finished else status_not_started,
        },
        {
            'period_order': 2,
            'description':  '2. połowa',
            'limit':        2700000,
            'initial_time': 2700000,   # zaczyna od 45:00
            'home_team_goals': home_2h,
            'away_team_goals': away_2h,
            'status': status_finished if is_finished else status_not_started,
        },
    ]

    for pd in periods_data:
        existing = period_model.query.filter_by(
            game_id=game.id,
            period_order=pd['period_order'],
        ).first()

        if existing:
            existing.home_team_goals = pd['home_team_goals']
            existing.away_team_goals = pd['away_team_goals']
            existing.status          = pd['status']
            existing.updated_at      = datetime.utcnow()
        else:
            period = period_model(
                game_id          = game.id,
                period_order     = pd['period_order'],
                description      = pd['description'],
                limit            = pd['limit'],
                initial_time     = pd['initial_time'],
                pause_at_limit   = True,
                home_team_goals  = pd['home_team_goals'],
                away_team_goals  = pd['away_team_goals'],
                status           = pd['status'],
            )
            db_session.add(period)