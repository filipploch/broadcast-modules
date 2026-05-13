"""Banner Manager - handles CRUD operations for Banner model"""
import logging

from core.extensions import db

logger = logging.getLogger(__name__)


def _get_banner():
    from core.models.base_banner import get_banner_model
    return get_banner_model()


class BannerManager:

    def get_all_banners(self):
        Banner = _get_banner()
        return Banner.query.order_by(Banner.order, Banner.name).all()

    def get_banner_by_id(self, banner_id: int):
        Banner = _get_banner()
        return Banner.query.get(banner_id)

    def create_banner(self, name: str, source: str, order: int = 0,
                      is_visible: bool = True, activation_function: str = None):
        try:
            Banner = _get_banner()
            banner = Banner(
                name=name,
                source=source,
                order=order,
                is_visible=is_visible,
                activation_function=activation_function or None,
            )
            db.session.add(banner)
            db.session.commit()
            logger.info(f"Created banner: {banner.name}")
            return banner
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating banner: {e}")
            return None

    def update_banner(self, banner_id: int, name: str, source: str, order: int,
                      is_visible: bool, activation_function: str = None):
        banner = self.get_banner_by_id(banner_id)
        if not banner:
            return None
        try:
            banner.name = name
            banner.source = source
            banner.order = order
            banner.is_visible = is_visible
            banner.activation_function = activation_function or None
            db.session.commit()
            logger.info(f"Updated banner ID {banner_id}")
            return banner
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating banner: {e}")
            return None

    def delete_banner(self, banner_id: int) -> bool:
        banner = self.get_banner_by_id(banner_id)
        if not banner:
            return False
        try:
            db.session.delete(banner)
            db.session.commit()
            logger.info(f"Deleted banner ID {banner_id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting banner: {e}")
            return False
