"""GameEvent Manager - handles game events timeline"""
import math
from dataclasses import dataclass, field
from typing import List, Optional
from app.extensions import db
from app.models.game_event import GameEvent
from app.models.event import Event
from app.models.game import Game
from app.models.period import Period
from app.models.team import Team
from app.models.player import Player
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class GoalEntry:
    """
    Single goal entry for the scorers summary.

    Attributes:
        player_id:          DB id zawodnika (None dla anonimowej bramki)
        player_first_name:  Imię zawodnika
        player_last_name:   Nazwisko zawodnika
        player_number:      Numer na koszulce
        minute:             Minuta zdobycia bramki (1-based, zaokrąglona w górę)
        added_time:         Minuty doliczonego czasu (None jeśli w czasie regulaminowym)
        period_order:       Numer części meczu (1 = pierwsza połowa, 2 = druga, …)
        period_description: Czytelny opis części meczu (np. „1. połowa")
        is_own_goal:        True jeśli bramka samobójcza
        team_id:            DB id drużyny, na konto której wpisana bramka
        game_time_s:        Surowy czas gry w sekundach (do sortowania)
    """
    player_id:          Optional[int]
    player_first_name:  Optional[str]
    player_last_name:   Optional[str]
    player_number:      Optional[int]
    minute:             int
    added_time:         Optional[int]
    period_order:       int
    period_description: str
    is_own_goal:        bool
    team_id:            int
    game_time_s:        int

    @property
    def minute_display(self) -> str:
        """Zwraca czas w formacie wyświetlania, np. '10\'' lub '90+2\''."""
        if self.added_time:
            return f"{self.minute}+{self.added_time}'"
        return f"{self.minute}'"


@dataclass
class ScorerEntry:
    """
    Jeden strzelec i wszystkie jego bramki dla danej drużyny.

    Attributes:
        player_id:          DB id zawodnika (None = anonimowa)
        player_first_name:  Imię zawodnika
        player_last_name:   Nazwisko zawodnika
        player_number:      Numer na koszulce
        goals:              Lista GoalEntry posortowana chronologicznie
    """
    player_id:         Optional[int]
    player_first_name: Optional[str]
    player_last_name:  Optional[str]
    player_number:     Optional[int]
    goals: List[GoalEntry] = field(default_factory=list)


@dataclass
class TeamGoalsSummary:
    """
    Zestawienie bramek jednej drużyny z podziałem na strzelców.
    Strzelcy posortowani wg czasu pierwszej bramki (chronologicznie).

    Attributes:
        team_id:  DB id drużyny
        team_name: Pełna nazwa drużyny
        scorers:  Lista ScorerEntry
    """
    team_id: int
    team_name: str
    scorers: List[ScorerEntry] = field(default_factory=list)


@dataclass
class GameGoalsSummary:
    """
    Kompletne zestawienie bramek meczu z podziałem na drużyny.

    Attributes:
        game_id:    DB id meczu
        home:       Bramki strzelone na konto drużyny gospodarzy
        away:       Bramki strzelone na konto drużyny gości
    """
    game_id: int
    home: TeamGoalsSummary
    away: TeamGoalsSummary


class GameEventManager:
    """Manager for GameEvent operations"""

    def record_event(self, game_id: int, event_id: int, game_time: int = None,
                    period_id: int = None, team_id: int = None,
                    player_id: int = None, event_place: str = None,
                    replay_end_time: int = None, video_path: str = None,
                    color: str = '#000000', comment: str = None) -> Optional[GameEvent]:
        """
        Record event in a game

        Args:
            game_id: Game ID
            event_id: Event type ID
            game_time: Game time in milliseconds (from timer plugin)
            replay_end_time: Wall-clock recording time in milliseconds
            video_path: Path to the video file associated with the event
            period_id: Period ID (optional, auto-detect current if not provided)
            team_id: Team ID (required if Event.is_reported=True)
            player_id: Player ID (required if Event.is_reported=True)
            event_place: Location on the field where the event occurred (optional)

        home_team_goals and away_team_goals are populated automatically from the
        current score in the games table at the moment of recording.

        Returns:
            GameEvent object or None if error

        Raises:
            ValueError if validation fails
        """
        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Validate event exists
        event = Event.query.get(event_id)
        if not event:
            raise ValueError(f"Typ zdarzenia o ID {event_id} nie istnieje")

        # Auto-detect current period if not provided
        if period_id is None:
            current_period = game.get_current_period()
            if not current_period:
                raise ValueError(f"Brak aktywnej części meczu dla game_id={game_id}")
            period_id = current_period.id
        else:
            # Validate period exists and belongs to game
            period = Period.query.get(period_id)
            if not period or period.game_id != game_id:
                raise ValueError(f"Część o ID {period_id} nie istnieje lub nie należy do meczu {game_id}")

        # Validate team for reported events (player_id is optional)
        if event.is_reported and team_id is not None:
            team = Team.query.get(team_id)
            if not team:
                raise ValueError(f"Drużyna o ID {team_id} nie istnieje")

        if player_id is not None:
            player = Player.query.get(player_id)
            if not player:
                raise ValueError(f"Zawodnik o ID {player_id} nie istnieje")

        try:
            replay_start_time = GameEvent.calc_replay_start_time(replay_end_time) if replay_end_time is not None else None
            game_event = GameEvent(
                game_id=game_id,
                event_id=event_id,
                period_id=period_id,
                team_id=team_id,
                player_id=player_id,
                game_time=game_time,
                replay_start_time=replay_start_time,
                replay_end_time=replay_end_time,
                video_path=video_path,
                event_place=event_place,
                home_team_goals=game.home_team_goals,
                away_team_goals=game.away_team_goals,
                # color=color,
                comment=comment,
            )
            db.session.add(game_event)
            db.session.commit()

            logger.info(f"Recorded event '{event.name}' at {game_event.game_time_formatted} in game {game_id}")
            return game_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error recording event: {e}")
            raise

    def record_event_now(self, game_id: int, event_id: int,
                        replay_end_time: int, video_path: str,
                        team_id: int = None, player_id: int = None,
                        event_place: str = None,
                        get_game_time_func=None) -> Optional[GameEvent]:
        """
        Record event with current game time from timer plugin

        Args:
            game_id: Game ID
            event_id: Event type ID
            replay_end_time: Wall-clock recording time in milliseconds
            video_path: Path to the video file associated with the event
            team_id: Team ID (optional, required if Event.is_reported=True)
            player_id: Player ID (optional, required if Event.is_reported=True)
            event_place: Location on the field where the event occurred (optional)
            get_game_time_func: Function to get current game time from timer (optional)
                                If not provided, uses 0 as fallback

        Returns:
            GameEvent object or None if error
        """
        # Get current game time from timer
        if get_game_time_func:
            try:
                current_game_time = get_game_time_func()
            except Exception as e:
                logger.warning(f"Could not get game time from timer: {e}, using 0")
                current_game_time = 0
        else:
            current_game_time = 0
            logger.warning("No get_game_time_func provided, using game_time=0")

        return self.record_event(
            game_id=game_id,
            event_id=event_id,
            game_time=current_game_time,
            replay_end_time=replay_end_time,
            video_path=video_path,
            team_id=team_id,
            player_id=player_id,
            event_place=event_place
        )

    def get_events_for_game(self, game_id: int, period_id: int = None,
                           event_id: int = None, team_id: int = None) -> List[GameEvent]:
        """
        Get events for a game with optional filters
        
        Args:
            game_id: Game ID
            period_id: Optional filter by period
            event_id: Optional filter by event type
            team_id: Optional filter by team

        Returns:
            List of GameEvent objects ordered by time
        """
        query = GameEvent.query.filter_by(game_id=game_id)
        
        if period_id:
            query = query.filter_by(period_id=period_id)
        if event_id:
            query = query.filter_by(event_id=event_id)
        if team_id:
            query = query.filter_by(team_id=team_id)

        return query.order_by(GameEvent.game_time).all()

    def get_game_event_by_id(self, game_event_id: int) -> Optional[GameEvent]:
        """Get GameEvent by ID"""
        return GameEvent.query.get(game_event_id)

    def update_game_event(self, game_event_id: int, event_id: int = None, game_time: int = None,
                        replay_end_time: int = None, replay_start_time: int = None, video_path: str = None,
                        event_place: str = None, team_id: int = None, player_id: int = None,
                        home_team_goals: int = None, away_team_goals: int = None) -> Optional[GameEvent]:
        """
        Update game event

        Args:
            game_event_id: GameEvent ID
            event_id: New event type ID (optional)
            game_time: New game time in milliseconds (optional)
            replay_end_time: New wall-clock recording time in milliseconds (optional)
            video_path: New path to the video file (optional)
            event_place: New location on the field (optional)
            team_id: New team ID (optional)
            player_id: New player ID (optional)
            home_team_goals: Score snapshot — home team (optional, from UI)
            away_team_goals: Score snapshot — away team (optional, from UI)

        Returns:
            Updated GameEvent object or None if error
        """
        game_event = self.get_game_event_by_id(game_event_id)
        if not game_event:
            logger.warning(f"GameEvent with ID {game_event_id} not found")
            return None

        try:
            if event_id is not None:
                event = Event.query.get(event_id)
                if not event:
                    raise ValueError(f"Typ zdarzenia o ID {event_id} nie istnieje")
                game_event.event_id = event_id
            if game_time is not None:
                game_event.game_time = game_time
            if replay_end_time is not None:
                game_event.replay_start_time = GameEvent.calc_replay_start_time(replay_end_time)
                game_event.replay_end_time = replay_end_time
            if replay_start_time is not None:
                game_event.replay_start_time = replay_start_time
            if video_path is not None:
                game_event.video_path = video_path
            if event_place is not None:
                game_event.event_place = event_place
            if team_id is not None:
                game_event.team_id = team_id
            if player_id is not None:
                game_event.player_id = player_id
            if home_team_goals is not None:
                game_event.home_team_goals = home_team_goals
            if away_team_goals is not None:
                game_event.away_team_goals = away_team_goals

            db.session.commit()
            logger.info(f"Updated GameEvent ID {game_event_id}")
            return game_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating game event: {e}")

    def delete_game_event(self, game_event_id: int) -> bool:
        """
        Delete game event

        Args:
            game_event_id: GameEvent ID

        Returns:
            True if deleted, False if error
        """
        game_event = self.get_game_event_by_id(game_event_id)
        if not game_event:
            logger.warning(f"GameEvent with ID {game_event_id} not found")
            return False

        try:
            db.session.delete(game_event)
            db.session.commit()
            logger.info(f"Deleted GameEvent ID {game_event_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting game event: {e}")
            return False

    def get_timeline(self, game_id: int) -> List[GameEvent]:
        """
        Get complete timeline of events for a game
        
        Returns events ordered by time with full details.

        Args:
            game_id: Game ID

        Returns:
            List of GameEvent objects with all relationships loaded
        """
        return GameEvent.query.filter_by(game_id=game_id).order_by(GameEvent.game_time).all()

    # -----------------------------------------------------------------------
    # Goals summary
    # -----------------------------------------------------------------------

    def get_goals_summary(self, game_id: int) -> GameGoalsSummary:
        """
        Pobiera zestawienie strzelców bramek dla wskazanego meczu,
        z podziałem na drużyny.

        Bramki samobójcze (event.player_from_opponent = True) są przypisywane
        do drużyny przeciwnej względem team_id zdarzenia, tak jak w rzeczywistości
        (tj. gol wpada do bramki drużyny, do której należy zawodnik).

        Czas bramki obliczany jest na podstawie game_time (ms) oraz limitu
        poprzednich części (period.initial_time), co pozwala wydzielić minuty
        doliczonego czasu gry.

        Args:
            game_id: ID meczu

        Returns:
            GameGoalsSummary z bramkami pogrupowanymi na home / away

        Raises:
            ValueError: gdy mecz nie istnieje
        """
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Pobieramy wszystkie zdarzenia będące bramkami dla tego meczu.
        # Bramki identyfikujemy przez filter_class = 'goal' (obejmuje
        # zarówno zwykłe bramki, jak i samobójcze).
        goal_events: List[GameEvent] = (
            GameEvent.query
            .join(GameEvent.event)
            .filter(
                GameEvent.game_id == game_id,
                Event.filter_class == 'goal',
            )
            .order_by(GameEvent.game_time)
            .all()
        )

        home_summary = TeamGoalsSummary(
            team_id=game.home_team_id,
            team_name=game.home_team.name if game.home_team else str(game.home_team_id),
        )
        away_summary = TeamGoalsSummary(
            team_id=game.away_team_id,
            team_name=game.away_team.name if game.away_team else str(game.away_team_id),
        )

        # Słowniki pomocnicze: player_id -> ScorerEntry, osobno dla każdej drużyny.
        # None jako klucz obsługuje bramki bez przypisanego zawodnika.
        home_scorers: dict = {}
        away_scorers: dict = {}

        for ge in goal_events:
            entry = self._build_goal_entry(ge)
            if entry is None:
                continue

            is_own_goal = bool(ge.event and ge.event.player_from_opponent)

            # Bramka (zwykła lub samobójcza) jest zawsze przypisywana do słownika
            # drużyny której team_id nosi zdarzenie. Dla bramek samobójczych
            # team_id wskazuje drużynę która zdobyła punkt (przeciwną względem
            # zawodnika), a is_own_goal = True pozwala overlay wyświetlić adnotację.
            scorers = home_scorers if ge.team_id == game.home_team_id else away_scorers

            key = ge.player_id  # None dla anonimowych
            if key not in scorers:
                scorers[key] = ScorerEntry(
                    player_id=entry.player_id,
                    player_first_name=entry.player_first_name,
                    player_last_name=entry.player_last_name,
                    player_number=entry.player_number,
                )
            scorers[key].goals.append(entry)

        # Budujemy listy strzelców posortowane wg czasu pierwszej bramki
        home_summary.scorers = sorted(home_scorers.values(), key=lambda s: s.goals[0].game_time_s)
        away_summary.scorers = sorted(away_scorers.values(), key=lambda s: s.goals[0].game_time_s)

        return GameGoalsSummary(
            game_id=game_id,
            home=home_summary,
            away=away_summary,
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_goal_entry(ge: GameEvent) -> Optional[GoalEntry]:
        """
        Buduje obiekt GoalEntry na podstawie rekordu GameEvent.

        Logika czasu:
        - game_time (s) to czas globalny całego meczu w sekundach.
        - period.limit i period.initial_time są w ms — przeliczamy do sekund
          przez dzielenie przez 1000.
        - Minuta globalna = ceil(game_time_s / 60), min. 1.
        - Doliczony czas = nadwyżka ponad regulaminowy koniec tej części
          (period.limit / 1000).
        """
        if ge.game_time is None:
            logger.warning(f"GameEvent id={ge.id} nie ma game_time, pomijam")
            return None

        period: Optional[Period] = ge.period
        if period is None:
            logger.warning(f"GameEvent id={ge.id} nie ma przypisanej części meczu, pomijam")
            return None

        # Przelicz limity części z ms na sekundy
        period_limit_s = period.limit / 1000

        # Doliczony czas: nadwyżka ponad regulaminowy koniec tej części
        overtime_s = max(0, ge.game_time - period_limit_s)

        if overtime_s > 0:
            base_minute = max(1, math.ceil(period_limit_s / 60))
            added_time  = max(1, math.ceil(overtime_s / 60))
        else:
            base_minute = max(1, math.ceil(ge.game_time / 60))
            added_time  = None

        # Imię i nazwisko zawodnika jako osobne pola
        player_first_name: Optional[str] = None
        player_last_name:  Optional[str] = None
        player_number:     Optional[int] = None
        if ge.player:
            player_first_name = ge.player.first_name or None
            player_last_name  = ge.player.last_name  or None
            player_number     = ge.player.number

        is_own_goal = bool(ge.event and ge.event.player_from_opponent)

        return GoalEntry(
            player_id=ge.player_id,
            player_first_name=player_first_name,
            player_last_name=player_last_name,
            player_number=player_number,
            minute=base_minute,
            added_time=added_time,
            period_order=period.period_order,
            period_description=period.description,
            is_own_goal=is_own_goal,
            team_id=ge.team_id,
            game_time_s=ge.game_time,
        )
