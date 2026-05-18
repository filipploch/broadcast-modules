from core.models.base_banner import BaseBannerMixin
from core.extensions import db


class Banner(BaseBannerMixin, db.Model):
    __tablename__ = 'banners'
