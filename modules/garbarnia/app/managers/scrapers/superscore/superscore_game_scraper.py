"""Superscore Game Scraper — scrapowanie wyników z API superscore.live

API endpoint:
    https://scorealarm-stats.freetls.fastly.net/v2/soccer/fixtures/season/plsuperscore/pl-PL
    ?season-id={season_id}&with-upcoming=yes

Dane meczu:
    match_state         0=NOT_STARTED, 1=IN_PROGRESS, 2=FINISHED
    match_date.seconds  Unix timestamp
    round_number        numer kolejki
    team1/team2         .names[type=1].value.string_value → pełna nazwa
    scores[type=0]      wynik końcowy (home/away)
    scores[type=1]      wynik do przerwy

Każdy mecz zwracany jako słownik z kluczami:
    round           int
    date            str  'YYYY-MM-DD HH:MM:SS+00:00'  (lub None)
    home_team_name  str
    away_team_name  str
    home_team_goals int | None
    away_team_goals int | None
    home_ht_goals   int | None
    away_ht_goals   int | None
    status          int  0=NOT_STARTED | 1=IN_PROGRESS | 2=FINISHED
"""
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

STATUS_NOT_STARTED = 0
STATUS_IN_PROGRESS = 1
STATUS_FINISHED    = 2

_MATCH_STATE_MAP = {
    0: STATUS_NOT_STARTED,
    1: STATUS_IN_PROGRESS,
    2: STATUS_FINISHED,
}

_API_BASE = (
    'https://scorealarm-stats.freetls.fastly.net'
    '/v2/soccer/fixtures/season/plsuperscore/pl-PL'
)


class SuperscoreGameScraper:
    """Scraper terminarza z API superscore.live."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent':  'Mozilla/5.0 (compatible; broadcast-scraper/1.0)',
            'Accept':      'application/json',
        })

    # ── Publiczne API ─────────────────────────────────────────────────────────

    def scrape_season(self, season_id: str, with_upcoming: bool = True) -> list[dict]:
        """
        Pobierz i sparsuj wszystkie mecze danego sezonu.

        Args:
            season_id:     ID sezonu z superscore.live (np. '4vDT5gZAVMkCxWuCYl8kzc')
            with_upcoming: True → zwróć też mecze nierozpoczęte

        Returns:
            Lista słowników z danymi meczów
        """
        params = {
            'season-id':    season_id,
            'with-upcoming': 'yes' if with_upcoming else 'no',
        }
        try:
            resp = self.session.get(_API_BASE, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data)
        except requests.RequestException as e:
            logger.error(f"Błąd pobierania z superscore API: {e}")
            return []
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd scrapowania superscore: {e}", exc_info=True)
            return []

    def scrape_multiple_seasons(self, season_ids: list[str]) -> list[dict]:
        """Scrapuj wiele sezonów i zwróć połączoną listę meczów."""
        all_games = []
        for sid in season_ids:
            games = self.scrape_season(sid)
            all_games.extend(games)
            logger.info(f"Scrapowano {len(games)} meczów z sezonu {sid}")
        return all_games

    # ── Parsowanie ────────────────────────────────────────────────────────────

    def _parse_response(self, data: dict) -> list[dict]:
        events = data.get('events') or []
        games  = []
        for event in events:
            gd = self._parse_event(event)
            if gd:
                games.append(gd)
        logger.info(f"Sparsowano {len(games)} meczów z {len(events)} eventów")
        return games

    def _parse_event(self, event: dict) -> Optional[dict]:
        try:
            home_name = self._extract_team_name(event.get('team1') or {})
            away_name = self._extract_team_name(event.get('team2') or {})
            if not home_name or not away_name:
                return None

            match_state = event.get('match_state', 0)
            status      = _MATCH_STATE_MAP.get(match_state, STATUS_NOT_STARTED)

            round_nr  = event.get('round_number') or event.get('round') or 0
            date_str  = self._extract_date(event)

            ft_score = self._extract_score(event, score_type=0)
            ht_score = self._extract_score(event, score_type=1)

            # Dla meczu w trakcie — wynik cząstkowy jako goals, brak HT jeszcze
            home_goals = ft_score[0] if ft_score else (
                self._extract_live_score(event, 'home') if status == STATUS_IN_PROGRESS else None
            )
            away_goals = ft_score[1] if ft_score else (
                self._extract_live_score(event, 'away') if status == STATUS_IN_PROGRESS else None
            )

            return {
                'round':           round_nr,
                'date':            date_str,
                'home_team_name':  home_name,
                'away_team_name':  away_name,
                'home_team_goals': home_goals,
                'away_team_goals': away_goals,
                'home_ht_goals':   ht_score[0] if ht_score else None,
                'away_ht_goals':   ht_score[1] if ht_score else None,
                'status':          status,
            }
        except Exception as e:
            logger.error(f"Błąd parsowania eventu: {e}", exc_info=True)
            return None

    # ── Helpery ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_team_name(team: dict) -> Optional[str]:
        """Wyciągnij pełną nazwę drużyny z names[type=1]."""
        for entry in team.get('names') or []:
            if entry.get('type') == 1:
                val = entry.get('value') or {}
                name = val.get('string_value') or val.get('stringValue') or ''
                return name.strip() or None
        # Fallback: pierwszy dostępny
        for entry in team.get('names') or []:
            val = entry.get('value') or {}
            name = val.get('string_value') or val.get('stringValue') or ''
            if name.strip():
                return name.strip()
        return None

    @staticmethod
    def _extract_score(event: dict, score_type: int) -> Optional[tuple[int, int]]:
        """
        Zwróć (home, away) dla danego score_type.
        score_type=0 → wynik końcowy, score_type=1 → do przerwy.
        API zwraca: {"team1": <home_goals>, "team2": <away_goals>, "type": <int>}
        """
        for score in event.get('scores') or []:
            if score.get('type') == score_type:
                home = score.get('team1')
                away = score.get('team2')
                if home is not None and away is not None:
                    return int(home), int(away)
        return None

    @staticmethod
    def _extract_live_score(event: dict, side: str) -> Optional[int]:
        """Wyciągnij bieżący wynik live z scores[type=0] (team1=home, team2=away)."""
        key = 'team1' if side == 'home' else 'team2'
        for score in event.get('scores') or []:
            if score.get('type') == 0:
                val = score.get(key)
                return int(val) if val is not None else None
        return None

    @staticmethod
    def _warsaw_offset_seconds(dt_utc: datetime) -> int:
        """
        Zwróć offset strefy Europa/Warszawa w sekundach dla podanej daty UTC.
        Reguła UE: CEST (UTC+2) od ostatniej niedzieli marca 01:00 UTC
                   do ostatniej niedzieli października 01:00 UTC.
        Poza tym CET (UTC+1).
        """
        year = dt_utc.year

        def _last_sunday(y: int, month: int) -> datetime:
            last = datetime(y, month, 31 if month in (1,3,5,7,8,10,12) else 30)
            return last - timedelta(days=(last.weekday() + 1) % 7)

        cest_start = _last_sunday(year, 3).replace(hour=1)
        cest_end   = _last_sunday(year, 10).replace(hour=1)

        if cest_start <= dt_utc < cest_end:
            return 7200  # UTC+2
        return 3600      # UTC+1

    @staticmethod
    def _extract_date(event: dict) -> Optional[str]:
        """
        Parsuj match_date.seconds (Unix timestamp UTC) → czas lokalny PL (CET/CEST).
        Format zgodny z konwencją bazy: 'YYYY-MM-DD HH:MM:SS+00:00'
        (czas lokalny z sufiksem +00:00, jak scraper MZPN).
        """
        match_date = event.get('match_date') or {}
        seconds    = match_date.get('seconds')
        if seconds is None:
            seconds = event.get('start_time') or event.get('startTime')
        if seconds is None:
            return None
        try:
            dt_utc   = datetime.fromtimestamp(int(seconds), tz=timezone.utc).replace(tzinfo=None)
            offset   = SuperscoreGameScraper._warsaw_offset_seconds(dt_utc)
            dt_local = dt_utc + timedelta(seconds=offset)
            return dt_local.strftime('%Y-%m-%d %H:%M:%S+00:00')
        except (ValueError, OSError):
            return None
