"""GameReferee Manager - handles referee assignments to games"""
from typing import List, Optional
from app.extensions import db
from app.models.game_referee import GameReferee
from app.models.referee import Referee
from app.models.game import Game
import logging

logger = logging.getLogger(__name__)


class GameRefereeManager:
    """Manager for GameReferee operations"""

    def assign_referee_to_game(self, game_id: int, referee_id: int,
                               referee_type: str) -> Optional[GameReferee]:
        """
        Assign referee to game

        Args:
            game_id: Game ID
            referee_id: Referee ID
            referee_type: Referee type ("Główny" or "Asystent")

        Returns:
            GameReferee object or None if error

        Raises:
            ValueError if game/referee not found, invalid type, or referee already assigned
        """
        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Validate referee exists
        referee = Referee.query.get(referee_id)
        if not referee:
            raise ValueError(f"Sędzia o ID {referee_id} nie istnieje")

        # Validate referee type
        if not GameReferee.is_valid_type(referee_type):
            valid_types = ', '.join(GameReferee.REFEREE_TYPES)
            raise ValueError(f"Nieprawidłowy typ sędziego: {referee_type}. Dozwolone: {valid_types}")

        # Check if referee already assigned
        existing = GameReferee.query.filter_by(game_id=game_id, referee_id=referee_id).first()
        if existing:
            raise ValueError(f"Sędzia {referee.full_name} jest już przypisany do meczu {game_id}")

        try:
            game_referee = GameReferee(
                game_id=game_id,
                referee_id=referee_id,
                type=referee_type
            )
            db.session.add(game_referee)
            db.session.commit()

            logger.info(f"Assigned referee {referee.full_name} ({referee_type}) to game {game_id}")
            return game_referee

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning referee to game: {e}")
            raise

    def get_referees_for_game(self, game_id: int, referee_type: str = None) -> List[GameReferee]:
        """
        Get all referees assigned to a game
        
        Args:
            game_id: Game ID
            referee_type: Optional filter by type

        Returns:
            List of GameReferee objects
        """
        query = GameReferee.query.filter_by(game_id=game_id)
        if referee_type:
            query = query.filter_by(type=referee_type)
        return query.all()

    def get_main_referee(self, game_id: int) -> Optional[GameReferee]:
        """Get main referee for a game"""
        return GameReferee.query.filter_by(
            game_id=game_id,
            type=GameReferee.TYPE_MAIN
        ).first()

    def get_assistant_referees(self, game_id: int) -> List[GameReferee]:
        """Get assistant referees for a game"""
        return GameReferee.query.filter_by(
            game_id=game_id,
            type=GameReferee.TYPE_ASSISTANT
        ).all()

    def get_game_referee_by_id(self, game_referee_id: int) -> Optional[GameReferee]:
        """Get GameReferee by ID"""
        return GameReferee.query.get(game_referee_id)

    def update_game_referee(self, game_referee_id: int,
                           referee_type: str = None) -> Optional[GameReferee]:
        """
        Update game referee assignment
        
        Args:
            game_referee_id: GameReferee ID
            referee_type: New referee type (optional)

        Returns:
            Updated GameReferee object or None if error

        Raises:
            ValueError if invalid referee type
        """
        game_referee = self.get_game_referee_by_id(game_referee_id)
        if not game_referee:
            logger.warning(f"GameReferee with ID {game_referee_id} not found")
            return None

        try:
            if referee_type is not None:
                if not GameReferee.is_valid_type(referee_type):
                    valid_types = ', '.join(GameReferee.REFEREE_TYPES)
                    raise ValueError(f"Nieprawidłowy typ sędziego: {referee_type}. Dozwolone: {valid_types}")
                game_referee.type = referee_type

            db.session.commit()
            logger.info(f"Updated GameReferee ID {game_referee_id}")
            return game_referee

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating game referee: {e}")
            raise

    def remove_referee_from_game(self, game_referee_id: int) -> bool:
        """
        Remove referee from game

        Args:
            game_referee_id: GameReferee ID

        Returns:
            True if removed, False if error
        """
        game_referee = self.get_game_referee_by_id(game_referee_id)
        if not game_referee:
            logger.warning(f"GameReferee with ID {game_referee_id} not found")
            return False

        try:
            db.session.delete(game_referee)
            db.session.commit()
            logger.info(f"Removed referee from game (GameReferee ID: {game_referee_id})")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing referee from game: {e}")
            return False

    def get_games_for_referee(self, referee_id: int) -> List[GameReferee]:
        """Get all games where referee officiated"""
        return GameReferee.query.filter_by(referee_id=referee_id).all()
