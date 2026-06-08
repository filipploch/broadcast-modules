"""CameraPositionCalibration — moduł garbarnia."""
from core.models.base_camera_position_calibration import BaseCameraPositionCalibrationMixin
from core.extensions import db


class CameraPositionCalibration(BaseCameraPositionCalibrationMixin, db.Model):
    __tablename__ = 'camera_position_calibrations'
