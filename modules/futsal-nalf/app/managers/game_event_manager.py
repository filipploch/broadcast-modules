"""GameEvent Manager - handles game events timeline"""
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


class GameEventManager:
    """Manager for GameEvent operations"""

    def record_event(self, game_id: int, event_id: int, time: int,
                    period_id: int = None, team_id: int = None,
                    player_id: int = None) -> Optional[GameEvent]:
        """
        Record event in a game
        
        Args:
            game_id: Game ID
            event_id: Event type ID
            time: Time in milliseconds (from timer plugin)
            period_id: Period ID (optional, auto-detect current if not provided)
            team_id: Team ID (required if Event.is_reported=True)
            player_id: Player ID (required if Event.is_reported=True)

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

        # Validate team/player for reported events
        if event.is_reported:
            if team_id is None:
                raise ValueError(f"Zdarzenie '{event.name}' wymaga przypisania do drużyny (team_id)")
            if player_id is None:
                raise ValueError(f"Zdarzenie '{event.name}' wymaga przypisania do zawodnika (player_id)")
            
            # Validate team exists
            team = Team.query.get(team_id)
            if not team:
                raise ValueError(f"Drużyna o ID {team_id} nie istnieje")
            
            # Validate player exists
            player = Player.query.get(player_id)
            if not player:
                raise ValueError(f"Zawodnik o ID {player_id} nie istnieje")

        try:
            game_event = GameEvent(
                game_id=game_id,
                event_id=event_id,
                period_id=period_id,
                team_id=team_id,
                player_id=player_id,
                time=time
            )
            db.session.add(game_event)
            db.session.commit()

            logger.info(f"Recorded event '{event.name}' at {game_event.time_formatted} in game {game_id}")
            return game_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error recording event: {e}")
            raise

    def record_event_now(self, game_id: int, event_id: int,
                        team_id: int = None, player_id: int = None,
                        get_time_func=None) -> Optional[GameEvent]:
        """
        Record event with current time from timer plugin
        
        Args:
            game_id: Game ID
            event_id: Event type ID
            team_id: Team ID (optional, required if Event.is_reported=True)
            player_id: Player ID (optional, required if Event.is_reported=True)
            get_time_func: Function to get current time from timer (optional)
                          If not provided, uses 0 as fallback

        Returns:
            GameEvent object or None if error
        """
        # Get current time from timer
        if get_time_func:
            try:
                current_time = get_time_func()
            except Exception as e:
                logger.warning(f"Could not get time from timer: {e}, using 0")
                current_time = 0
        else:
            current_time = 0
            logger.warning("No get_time_func provided, using time=0")

        return self.record_event(
            game_id=game_id,
            event_id=event_id,
            time=current_time,
            team_id=team_id,
            player_id=player_id
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

        return query.order_by(GameEvent.time).all()

    def get_game_event_by_id(self, game_event_id: int) -> Optional[GameEvent]:
        """Get GameEvent by ID"""
        return GameEvent.query.get(game_event_id)

    def update_game_event(self, game_event_id: int, time: int = None,
                         team_id: int = None, player_id: int = None) -> Optional[GameEvent]:
        """
        Update game event
        
        Args:
            game_event_id: GameEvent ID
            time: New time in milliseconds (optional)
            team_id: New team ID (optional)
            player_id: New player ID (optional)

        Returns:
            Updated GameEvent object or None if error
        """
        game_event = self.get_game_event_by_id(game_event_id)
        if not game_event:
            logger.warning(f"GameEvent with ID {game_event_id} not found")
            return None

        try:
            if time is not None:
                game_event.time = time
            if team_id is not None:
                game_event.team_id = team_id
            if player_id is not None:
                game_event.player_id = player_id

            db.session.commit()
            logger.info(f"Updated GameEvent ID {game_event_id}")
            return game_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating game event: {e}")
            return None

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
        return GameEvent.query.filter_by(game_id=game_id).order_by(GameEvent.time).all()
