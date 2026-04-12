"""GameCommentator Manager - handles commentator assignments to games"""
from typing import List, Optional
from app.extensions import db
from app.models.game_commentator import GameCommentator
from app.models.commentator import Commentator
from app.models.game import Game
import logging

logger = logging.getLogger(__name__)


class GameCommentatorManager:
    """Manager for GameCommentator operations"""

    def assign_commentator_to_game(self, game_id: int, commentator_id: int,
                               commentator_type: str) -> Optional[GameCommentator]:
        """
        Assign commentator to game

        Args:
            game_id: Game ID
            commentator_id: Commentator ID
            commentator_type: Commentator type ("Główny" or "Asystent")

        Returns:
            GameCommentator object or None if error

        Raises:
            ValueError if game/commentator not found, invalid type, or commentator already assigned
        """
        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Validate commentator exists
        commentator = Commentator.query.get(commentator_id)
        if not commentator:
            raise ValueError(f"Sędzia o ID {commentator_id} nie istnieje")

        # Validate commentator type
        if not GameCommentator.is_valid_type(commentator_type):
            valid_types = ', '.join(GameCommentator.REFEREE_TYPES)
            raise ValueError(f"Nieprawidłowy typ sędziego: {commentator_type}. Dozwolone: {valid_types}")

        # Check if commentator already assigned
        existing = GameCommentator.query.filter_by(game_id=game_id, commentator_id=commentator_id).first()
        if existing:
            raise ValueError(f"Sędzia {commentator.full_name} jest już przypisany do meczu {game_id}")

        try:
            game_commentator = GameCommentator(
                game_id=game_id,
                commentator_id=commentator_id,
                type=commentator_type
            )
            db.session.add(game_commentator)
            db.session.commit()

            logger.info(f"Assigned commentator {commentator.full_name} ({commentator_type}) to game {game_id}")
            return game_commentator

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning commentator to game: {e}")
            raise

    def get_commentators_for_game(self, game_id: int, commentator_type: str = None) -> List[GameCommentator]:
        """
        Get all commentators assigned to a game
        
        Args:
            game_id: Game ID
            commentator_type: Optional filter by type

        Returns:
            List of GameCommentator objects
        """
        query = GameCommentator.query.filter_by(game_id=game_id)
        if commentator_type:
            query = query.filter_by(type=commentator_type)
        return query.all()

    def get_main_commentator(self, game_id: int) -> Optional[GameCommentator]:
        """Get main commentator for a game"""
        return GameCommentator.query.filter_by(
            game_id=game_id,
            type=GameCommentator.TYPE_MAIN
        ).first()

    def get_assistant_commentators(self, game_id: int) -> List[GameCommentator]:
        """Get assistant commentators for a game"""
        return GameCommentator.query.filter_by(
            game_id=game_id,
            type=GameCommentator.TYPE_ASSISTANT
        ).all()

    def get_game_commentator_by_id(self, game_commentator_id: int) -> Optional[GameCommentator]:
        """Get GameCommentator by ID"""
        return GameCommentator.query.get(game_commentator_id)

    def update_game_commentator(self, game_commentator_id: int,
                           commentator_type: str = None) -> Optional[GameCommentator]:
        """
        Update game commentator assignment
        
        Args:
            game_commentator_id: GameCommentator ID
            commentator_type: New commentator type (optional)

        Returns:
            Updated GameCommentator object or None if error

        Raises:
            ValueError if invalid commentator type
        """
        game_commentator = self.get_game_commentator_by_id(game_commentator_id)
        if not game_commentator:
            logger.warning(f"GameCommentator with ID {game_commentator_id} not found")
            return None

        try:
            if commentator_type is not None:
                if not GameCommentator.is_valid_type(commentator_type):
                    valid_types = ', '.join(GameCommentator.REFEREE_TYPES)
                    raise ValueError(f"Nieprawidłowy typ sędziego: {commentator_type}. Dozwolone: {valid_types}")
                game_commentator.type = commentator_type

            db.session.commit()
            logger.info(f"Updated GameCommentator ID {game_commentator_id}")
            return game_commentator

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating game commentator: {e}")
            raise

    def remove_commentator_from_game(self, game_commentator_id: int) -> bool:
        """
        Remove commentator from game

        Args:
            game_commentator_id: GameCommentator ID

        Returns:
            True if removed, False if error
        """
        game_commentator = self.get_game_commentator_by_id(game_commentator_id)
        if not game_commentator:
            logger.warning(f"GameCommentator with ID {game_commentator_id} not found")
            return False

        try:
            db.session.delete(game_commentator)
            db.session.commit()
            logger.info(f"Removed commentator from game (GameCommentator ID: {game_commentator_id})")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing commentator from game: {e}")
            return False

    def get_games_for_commentator(self, commentator_id: int) -> List[GameCommentator]:
        """Get all games where commentator officiated"""
        return GameCommentator.query.filter_by(commentator_id=commentator_id).all()
