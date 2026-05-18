from core.models.base_game_camera import (
    BaseGameCameraMixin,
    HDMI_TO_DEVICE,
    HDMI_DEFAULT_LOCATION,
    VALID_HDMI_INPUTS,
)
from core.extensions import db


class GameCamera(BaseGameCameraMixin, db.Model):
    __tablename__ = 'game_cameras'
