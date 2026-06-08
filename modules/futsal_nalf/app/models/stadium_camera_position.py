"""StadiumCameraPosition — moduł futsal_nalf."""
from core.models.base_stadium_camera_position import BaseStadiumCameraPositionMixin
from core.extensions import db


class StadiumCameraPosition(BaseStadiumCameraPositionMixin, db.Model):
    __tablename__ = 'stadium_camera_positions'
