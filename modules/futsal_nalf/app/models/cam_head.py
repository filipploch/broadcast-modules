"""CamHead — moduł futsal_nalf."""
from core.models.base_cam_head import BaseCamHeadMixin
from core.extensions import db


class CamHead(BaseCamHeadMixin, db.Model):
    __tablename__ = 'cam_heads'
