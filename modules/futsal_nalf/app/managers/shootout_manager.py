"""Penalty Manager - handles penalty shootout operations"""
from typing import Optional
from core.extensions import db
from app.models.shootout import Shootout
from core.models.game import Game
import logging

logger = logging.getLogger(__name__)


class ShootoutManager:
    """Manager for Shootout (penalty shootout) operations"""

    def create_shootout(self, game_id: int, home_shootouts: int = 0, 
                                away_shootouts: int = 0) -> Optional[Shootout]:
        """
        Create penalty shootout for a game
        
        Args:
            game_id: Game ID
            home_shootouts: Home team shootout goals (default: 0)
            away_shootouts: Away team shootout goals (default: 0)
        
        Returns:
            Shootout object or None if error
        
        Raises:
            ValueError if game not found or penalty shootout already exists
        """
        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")
        
        # Check if penalty shootout already exists
        existing = Shootout.query.filter_by(game_id=game_id).first()
        if existing:
            raise ValueError(f"Konkurs rzutów karnych już istnieje dla meczu {game_id}")
        
        try:
            shootout = Shootout(
                game_id=game_id,
                home_team_shootouts=home_shootouts,
                away_team_shootouts=away_shootouts
            )
            db.session.add(shootout)
            db.session.commit()
            
            logger.info(f"Created penalty shootout for game {game_id}: {home_shootouts}:{away_shootouts}")
            return shootout
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating penalty shootout: {e}")
            raise

    def get_shootout_by_game(self, game_id: int) -> Optional[Shootout]:
        """Get penalty shootout for a game"""
        return Shootout.query.filter_by(game_id=game_id).first()

    def get_shootout_by_id(self, shootout_id: int) -> Optional[Shootout]:
        """Get penalty shootout by ID"""
        return Shootout.query.get(shootout_id)

    def update_shootout_score(self, shootout_id: int, home_shootouts: int, 
                            away_shootouts: int) -> Optional[Shootout]:
        """
        Update penalty shootout score
        
        Args:
            shootout_id: Shootout ID
            home_shootouts: Home team shootout goals
            away_shootouts: Away team shootout goals
        
        Returns:
            Updated Shootout object or None if error
        """
        shootout = self.get_shootout_by_id(shootout_id)
        if not shootout:
            logger.warning(f"Shootout with ID {shootout_id} not found")
            return None
        
        try:
            shootout.update_score(home_shootouts, away_shootouts)
            db.session.commit()
            
            logger.info(f"Updated shootout {shootout_id} score: {home_shootouts}:{away_shootouts}")
            return shootout
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating shootout score: {e}")
            return None

    def increment_shootout_goal(self, shootout_id: int, team: str) -> Optional[Shootout]:
        """
        Increment shootout goal for a team
        
        Args:
            shootout_id: Shootout ID
            team: 'home' or 'away'
        
        Returns:
            Updated Shootout object or None if error
        """
        shootout = self.get_shootout_by_id(shootout_id)
        if not shootout:
            logger.warning(f"Shootout with ID {shootout_id} not found")
            return None
        
        try:
            if team.lower() == 'home':
                shootout.increment_home_shootouts()
            elif team.lower() == 'away':
                shootout.increment_away_shootouts()
            else:
                raise ValueError(f"Invalid team: {team}. Must be 'home' or 'away'")
            
            db.session.commit()
            
            logger.info(f"Incremented {team} shootout goal for shootout {shootout_id}")
            return shootout
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error incrementing shootout goal: {e}")
            return None

    def delete_shootout(self, shootout_id: int) -> bool:
        """
        Delete penalty shootout
        
        Args:
            shootout_id: Shootout ID
        
        Returns:
            True if deleted, False if error
        """
        shootout = self.get_shootout_by_id(shootout_id)
        if not shootout:
            logger.warning(f"Shootout with ID {shootout_id} not found")
            return False
        
        try:
            db.session.delete(shootout)
            db.session.commit()
            
            logger.info(f"Deleted penalty shootout {shootout_id}")
            return True
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting penalty shootout: {e}")
            return False

    def has_shootout(self, game_id: int) -> bool:
        """Check if game has penalty shootout"""
        return Shootout.query.filter_by(game_id=game_id).first() is not None