"""GameEvent model - Events occurring during a game"""
from app.extensions import db
from datetime import datetime
from sqlalchemy.orm import validates


class GameEvent(db.Model):
    """Game event (occurrence of an event type during a game)"""
    __tablename__ = 'game_events'

    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False, index=True)
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=False, index=True)

    # Optional: team and player (only if Event.is_reported = True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True, index=True)

    # Time in the game when event occurred (milliseconds from timer plugin)
    game_time = db.Column(db.Integer, nullable=True)

    # Location on the field where the event occurred
    event_place = db.Column(db.String, nullable=True)

    # Fallback video data (e.g. OBS stream output) — nullable, populated separately
    record_time = db.Column(db.Integer, nullable=True)   # file length at moment of event (ms)
    video_path = db.Column(db.String, nullable=True)     # path to fallback video file

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    event_cameras = db.relationship('EventCamera', backref='game_event', lazy='dynamic',
                                    cascade='all, delete-orphan')

    # Indexes
    __table_args__ = (
        db.Index('ix_game_event_game_time', 'game_id', 'game_time'),
        db.Index('ix_game_event_period', 'period_id', 'game_time'),
    )

    def __repr__(self):
        return f'<GameEvent game_id={self.game_id} event_id={self.event_id} game_time={self.game_time}ms>'

    @validates('game_time')
    def validate_game_time(self, key, value):
        if value is not None and not isinstance(value, int):
            raise TypeError("game_time must be an integer (milliseconds) or None")
        return value

    @validates('record_time')
    def validate_record_time(self, key, value):
        if value is not None and not isinstance(value, int):
            raise TypeError("record_time must be an integer (milliseconds)")
        return value

    @validates('video_path')
    def validate_video_path(self, key, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("video_path must be a string")
        return value

    @validates('event_place')
    def validate_event_place(self, key, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("event_place must be a string or None")
        return value

    @property
    def game_time_seconds(self):
        return self.game_time / 1000 if self.game_time else 0

    @property
    def game_time_formatted(self):
        seconds = int(self.game_time_seconds)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @property
    def has_camera_data(self):
        """True if at least one EventCamera record exists for this event."""
        return self.event_cameras.count() > 0

    def to_dict(self):
        return {
            'id': self.id,
            'game_id': self.game_id,
            'event_id': self.event_id,
            'event_name': self.event.name if self.event else None,
            'event_short_name': self.event.short_name if self.event else None,
            'period_id': self.period_id,
            'period_description': self.period.description if self.period else None,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'player_id': self.player_id,
            'player_name': self.player.full_name if self.player else None,
            'game_time': self.game_time,
            'game_time_seconds': self.game_time_seconds,
            'game_time_formatted': self.game_time_formatted,
            'event_place': self.event_place,
            'record_time': self.record_time,
            'video_path': self.video_path,
            'has_camera_data': self.has_camera_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
