"""BackgroundImage Manager - CRUD for background images"""
import logging

from core.extensions import db

logger = logging.getLogger(__name__)


def _get_model():
    from core.models.base_background_image import get_background_image_model
    return get_background_image_model()


class BackgroundImageManager:

    def get_all(self):
        M = _get_model()
        return M.query.order_by(M.order, M.name).all()

    def get_by_id(self, bg_id: int):
        M = _get_model()
        return M.query.get(bg_id)

    def get_active(self):
        M = _get_model()
        return M.query.filter_by(is_active=True).first()

    def create(self, name: str, path: str, order: int = 0,
               is_visible: bool = True, description: str = None):
        try:
            M = _get_model()
            bg = M(name=name, path=path, order=order,
                   is_visible=is_visible, description=description or None)
            db.session.add(bg)
            db.session.commit()
            logger.info(f"Created background image: {bg.name}")
            return bg
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating background image: {e}")
            return None

    def update(self, bg_id: int, name: str, path: str, order: int,
               is_visible: bool, description: str = None):
        bg = self.get_by_id(bg_id)
        if not bg:
            return None
        try:
            bg.name = name
            bg.path = path
            bg.order = order
            bg.is_visible = is_visible
            bg.description = description or None
            db.session.commit()
            logger.info(f"Updated background image ID {bg_id}")
            return bg
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating background image: {e}")
            return None

    def set_active(self, bg_id: int):
        M = _get_model()
        try:
            M.query.update({M.is_active: False})
            bg = self.get_by_id(bg_id)
            if bg:
                bg.is_active = True
            db.session.commit()
            return bg
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error setting active background: {e}")
            return None

    def delete(self, bg_id: int) -> bool:
        bg = self.get_by_id(bg_id)
        if not bg:
            return False
        try:
            db.session.delete(bg)
            db.session.commit()
            logger.info(f"Deleted background image ID {bg_id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting background image: {e}")
            return False
