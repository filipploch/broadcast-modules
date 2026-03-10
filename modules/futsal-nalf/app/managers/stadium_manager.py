"""Stadium Manager - handles CRUD operations for Stadium model"""
from typing import List, Optional
from app.extensions import db
from app.models.stadium import Stadium
import logging

logger = logging.getLogger(__name__)


class StadiumManager:
    """Manager for Stadium CRUD operations"""

    def create_stadium(self, name: str, address: str, city: str) -> Optional[Stadium]:
        try:
            stadium = Stadium(name=name, address=address, city=city)
            db.session.add(stadium)
            db.session.commit()
            logger.info(f"Created stadium: {stadium.name}, {stadium.city}")
            return stadium
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating stadium: {e}")
            raise

    def get_all_stadiums(self) -> List[Stadium]:
        return Stadium.query.order_by(Stadium.city, Stadium.name).all()

    def get_stadium_by_id(self, stadium_id: int) -> Optional[Stadium]:
        return Stadium.query.get(stadium_id)

    def update_stadium(self, stadium_id: int, name: str = None,
                       address: str = None, city: str = None) -> Optional[Stadium]:
        stadium = self.get_stadium_by_id(stadium_id)
        if not stadium:
            logger.warning(f"Stadium with ID {stadium_id} not found")
            return None
        try:
            if name is not None:
                stadium.name = name
            if address is not None:
                stadium.address = address
            if city is not None:
                stadium.city = city
            db.session.commit()
            logger.info(f"Updated stadium ID {stadium_id}")
            return stadium
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating stadium: {e}")
            raise

    def delete_stadium(self, stadium_id: int) -> bool:
        stadium = self.get_stadium_by_id(stadium_id)
        if not stadium:
            logger.warning(f"Stadium with ID {stadium_id} not found")
            return False
        try:
            db.session.delete(stadium)
            db.session.commit()
            logger.info(f"Deleted stadium ID {stadium_id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting stadium: {e}")
            return False