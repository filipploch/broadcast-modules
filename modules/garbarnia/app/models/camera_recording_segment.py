from core.extensions import db
from core.models.base_camera_recording_segment import BaseCameraRecordingSegmentMixin


class CameraRecordingSegment(BaseCameraRecordingSegmentMixin, db.Model):
    __tablename__ = 'camera_recording_segments'
