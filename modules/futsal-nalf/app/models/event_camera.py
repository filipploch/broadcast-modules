"""EventCamera model - Camera recording data for a specific game event"""
from app.extensions import db
from datetime import datetime
from sqlalchemy.orm import validates


class EventCamera(db.Model):
    """
    Links a game event to the recording data from a specific camera.

    For each game event, one record per camera that was active at the time.
    Populated asynchronously via SocketIO response from recorder_device plugins.

    replay_end_time: length of the video file at the moment the event was recorded (ms).
                 Used as seek offset to find the event in the recording.
    """
    __tablename__ = 'event_cameras'

    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys
    game_event_id = db.Column(db.Integer, db.ForeignKey('game_events.id'),
                              nullable=False, index=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'),
                          nullable=False, index=True)

    # Recording data returned by recorder_device plugin
    video_path = db.Column(db.String, nullable=False)
    replay_start_time = db.Column(db.Integer, nullable=False)
    replay_end_time = db.Column(db.Integer, nullable=False)  # file length at event moment (ms)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # One camera cannot record the same event twice
    __table_args__ = (
        db.UniqueConstraint('game_event_id', 'camera_id', name='uix_event_camera'),
    )

    def __repr__(self):
        return f'<EventCamera game_event_id={self.game_event_id} camera_id={self.camera_id}>'

    @validates('replay_end_time')
    def validate_replay_end_time(self, key, value):
        if not isinstance(value, int):
            raise TypeError("replay_end_time must be an integer (milliseconds)")
        return value

    @validates('video_path')
    def validate_video_path(self, key, value):
        if not isinstance(value, str):
            raise TypeError("video_path must be a string")
        return value
    
    @staticmethod
    def calc_replay_start_time(replay_end_time: int) -> int:
        """Calculate replay_start_time from replay_end_time (10s before, min 0)."""
        return max(0, replay_end_time - 10000)

    @property
    def replay_end_time_formatted(self):
        """Seek offset as MM:SS"""
        seconds = int(self.replay_end_time / 1000)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def to_dict(self):
        return {
            'id': self.id,
            'game_event_id': self.game_event_id,
            'camera_id': self.camera_id,
            'camera_name': self.camera.name if self.camera else None,
            'video_path': self.video_path,
            'replay_start_time': self.replay_start_time,
            'replay_end_time': self.replay_end_time,
            'replay_end_time_formatted': self.replay_end_time_formatted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
