"""Penalty Manager - handles penalty shootout operations"""
from typing import Optional
from app.extensions import db
from app.models.penalty import Penalty
from app.models.game import Game
import logging

logger = logging.getLogger(__name__)


class PenaltyManager:
    """Manager for Penalty (penalty shootout) operations"""

    def create_penalty_shootout(self, game_id: int, home_penalties: int = 0, 
                                away_penalties: int = 0) -> Optional[Penalty]:
        """
        Create penalty shootout for a game
        
        Args:
            game_id: Game ID
            home_penalties: Home team penalty goals (default: 0)
            away_penalties: Away team penalty goals (default: 0)
        
        Returns:
            Penalty object or None if error
        
        Raises:
            ValueError if game not found or penalty shootout already exists
        """
        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")
        
        # Check if penalty shootout already exists
        existing = Penalty.query.filter_by(game_id=game_id).first()
        if existing:
            raise ValueError(f"Konkurs rzutów karnych już istnieje dla meczu {game_id}")
        
        try:
            penalty = Penalty(
                game_id=game_id,
                home_team_penalties=home_penalties,
                away_team_penalties=away_penalties
            )
            db.session.add(penalty)
            db.session.commit()
            
            logger.info(f"Created penalty shootout for game {game_id}: {home_penalties}:{away_penalties}")
            return penalty
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating penalty shootout: {e}")
            raise

    def get_penalty_by_game(self, game_id: int) -> Optional[Penalty]:
        """Get penalty shootout for a game"""
        return Penalty.query.filter_by(game_id=game_id).first()

    def get_penalty_by_id(self, penalty_id: int) -> Optional[Penalty]:
        """Get penalty shootout by ID"""
        return Penalty.query.get(penalty_id)

    def update_penalty_score(self, penalty_id: int, home_penalties: int, 
                            away_penalties: int) -> Optional[Penalty]:
        """
        Update penalty shootout score
        
        Args:
            penalty_id: Penalty ID
            home_penalties: Home team penalty goals
            away_penalties: Away team penalty goals
        
        Returns:
            Updated Penalty object or None if error
        """
        penalty = self.get_penalty_by_id(penalty_id)
        if not penalty:
            logger.warning(f"Penalty with ID {penalty_id} not found")
            return None
        
        try:
            penalty.update_score(home_penalties, away_penalties)
            db.session.commit()
            
            logger.info(f"Updated penalty {penalty_id} score: {home_penalties}:{away_penalties}")
            return penalty
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating penalty score: {e}")
            return None

    def increment_penalty_goal(self, penalty_id: int, team: str) -> Optional[Penalty]:
        """
        Increment penalty goal for a team
        
        Args:
            penalty_id: Penalty ID
            team: 'home' or 'away'
        
        Returns:
            Updated Penalty object or None if error
        """
        penalty = self.get_penalty_by_id(penalty_id)
        if not penalty:
            logger.warning(f"Penalty with ID {penalty_id} not found")
            return None
        
        try:
            if team.lower() == 'home':
                penalty.increment_home_penalties()
            elif team.lower() == 'away':
                penalty.increment_away_penalties()
            else:
                raise ValueError(f"Invalid team: {team}. Must be 'home' or 'away'")
            
            db.session.commit()
            
            logger.info(f"Incremented {team} penalty goal for penalty {penalty_id}")
            return penalty
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error incrementing penalty goal: {e}")
            return None

    def delete_penalty_shootout(self, penalty_id: int) -> bool:
        """
        Delete penalty shootout
        
        Args:
            penalty_id: Penalty ID
        
        Returns:
            True if deleted, False if error
        """
        penalty = self.get_penalty_by_id(penalty_id)
        if not penalty:
            logger.warning(f"Penalty with ID {penalty_id} not found")
            return False
        
        try:
            db.session.delete(penalty)
            db.session.commit()
            
            logger.info(f"Deleted penalty shootout {penalty_id}")
            return True
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting penalty shootout: {e}")
            return False

    def has_penalty_shootout(self, game_id: int) -> bool:
        """Check if game has penalty shootout"""
        return Penalty.query.filter_by(game_id=game_id).first() is not None