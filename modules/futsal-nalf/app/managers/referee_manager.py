"""Referee Manager - handles CRUD operations for Referee model"""
from typing import List, Optional
from app.extensions import db
from app.models.referee import Referee
import logging

logger = logging.getLogger(__name__)


class RefereeManager:
    """Manager for Referee CRUD operations"""

    def create_referee(self, first_name: str, last_name: str) -> Optional[Referee]:
        """
        Create new referee

        Args:
            first_name: Referee first name
            last_name: Referee last name

        Returns:
            Referee object or None if error
        """
        try:
            referee = Referee(
                first_name=first_name,
                last_name=last_name
            )
            db.session.add(referee)
            db.session.commit()

            logger.info(f"Created referee: {referee.full_name}")
            return referee

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating referee: {e}")
            return None

    def get_all_referees(self) -> List[Referee]:
        """Get all referees"""
        return Referee.query.order_by(Referee.last_name, Referee.first_name).all()

    def get_referee_by_id(self, referee_id: int) -> Optional[Referee]:
        """Get referee by ID"""
        return Referee.query.get(referee_id)

    def update_referee(self, referee_id: int, first_name: str = None,
                      last_name: str = None) -> Optional[Referee]:
        """
        Update referee

        Args:
            referee_id: Referee ID
            first_name: New first name (optional)
            last_name: New last name (optional)

        Returns:
            Updated Referee object or None if error
        """
        referee = self.get_referee_by_id(referee_id)
        if not referee:
            logger.warning(f"Referee with ID {referee_id} not found")
            return None

        try:
            if first_name is not None:
                referee.first_name = first_name
            if last_name is not None:
                referee.last_name = last_name

            db.session.commit()
            logger.info(f"Updated referee ID {referee_id}")
            return referee

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating referee: {e}")
            return None

    def delete_referee(self, referee_id: int) -> bool:
        """
        Delete referee
        
        Note: This will also delete all GameReferee assignments (cascade)

        Args:
            referee_id: Referee ID

        Returns:
            True if deleted, False if error
        """
        referee = self.get_referee_by_id(referee_id)
        if not referee:
            logger.warning(f"Referee with ID {referee_id} not found")
            return False

        try:
            referee_name = referee.full_name
            db.session.delete(referee)
            db.session.commit()
            logger.info(f"Deleted referee: {referee_name}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting referee: {e}")
            return False
