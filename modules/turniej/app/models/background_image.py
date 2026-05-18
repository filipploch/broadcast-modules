from core.models.base_background_image import BaseBackgroundImageMixin
from core.extensions import db


class BackgroundImage(BaseBackgroundImageMixin, db.Model):
    __tablename__ = 'background_images'
