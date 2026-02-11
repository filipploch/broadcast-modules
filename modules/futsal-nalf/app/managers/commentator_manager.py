"""Commentator Manager - handles CRUD operations for Commentator model"""
from typing import List, Optional
from app.extensions import db
from app.models.commentator import Commentator
import logging

logger = logging.getLogger(__name__)


class CommentatorManager:
    """Manager for Commentator CRUD operations"""

    def create_commentator(self, first_name: str, last_name: str) -> Optional[Commentator]:
        """
        Create new commentator

        Args:
            first_name: Commentator first name
            last_name: Commentator last name

        Returns:
            Commentator object or None if error
        """
        try:
            commentator = Commentator(
                first_name=first_name,
                last_name=last_name
            )
            db.session.add(commentator)
            db.session.commit()

            logger.info(f"Created commentator: {commentator.full_name}")
            return commentator

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating commentator: {e}")
            return None

    def get_all_commentators(self) -> List[Commentator]:
        """Get all commentators"""
        return Commentator.query.order_by(Commentator.last_name, Commentator.first_name).all()

    def get_commentator_by_id(self, commentator_id: int) -> Optional[Commentator]:
        """Get commentator by ID"""
        return Commentator.query.get(commentator_id)

    def update_commentator(self, commentator_id: int, first_name: str = None,
                      last_name: str = None) -> Optional[Commentator]:
        """
        Update commentator

        Args:
            commentator_id: Commentator ID
            first_name: New first name (optional)
            last_name: New last name (optional)

        Returns:
            Updated Commentator object or None if error
        """
        commentator = self.get_commentator_by_id(commentator_id)
        if not commentator:
            logger.warning(f"Commentator with ID {commentator_id} not found")
            return None

        try:
            if first_name is not None:
                commentator.first_name = first_name
            if last_name is not None:
                commentator.last_name = last_name

            db.session.commit()
            logger.info(f"Updated commentator ID {commentator_id}")
            return commentator

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating commentator: {e}")
            return None

    def delete_commentator(self, commentator_id: int) -> bool:
        """
        Delete commentator
        
        Note: This will also delete all GameCommentator assignments (cascade)

        Args:
            commentator_id: Commentator ID

        Returns:
            True if deleted, False if error
        """
        commentator = self.get_commentator_by_id(commentator_id)
        if not commentator:
            logger.warning(f"Commentator with ID {commentator_id} not found")
            return False

        try:
            commentator_name = commentator.full_name
            db.session.delete(commentator)
            db.session.commit()
            logger.info(f"Deleted commentator: {commentator_name}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting commentator: {e}")
            return False
