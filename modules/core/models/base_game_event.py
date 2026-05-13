"""GameEvent model - Events occurring during a game"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import validates, declared_attr
import re


class BaseGameEventMixin:
    """Game event (occurrence of an event type during a game)"""

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

    # Display colour for UI/overlay (hex, e.g. '#ff0000')
    # color = db.Column(db.String(7), nullable=False, default='#FFFFFF')

    # Optional free-text note added by the operator
    comment = db.Column(db.String, nullable=True)

    # Score at the moment the event occurred (snapshot from games table)
    home_team_goals = db.Column(db.Integer, nullable=True)
    away_team_goals = db.Column(db.Integer, nullable=True)

    # Fallback video data (e.g. OBS stream output) — nullable, populated separately
    replay_start_time = db.Column(db.Integer, nullable=True)
    replay_end_time = db.Column(db.Integer, nullable=True)   # file length at moment of event (ms)
    video_path = db.Column(db.String, nullable=True)     # path to fallback video file

    # Visibility flag — False means the event is hidden from the AKCJE view
    is_visible = db.Column(db.Boolean, nullable=False, default=True, server_default='1')

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    @declared_attr
    def event_cameras(cls):
        return db.relationship('EventCamera', backref='game_event', lazy='dynamic',
                                    cascade='all, delete-orphan')

    # Indexes
    @db.declared_attr
    def __table_args__(cls):
        return (
        db.Index('ix_game_event_game_time', 'game_id', 'game_time')
,
        db.Index('ix_game_event_period', 'period_id', 'game_time'),
    )

    def __repr__(self):
        return f'<GameEvent game_id={self.game_id} event_id={self.event_id} game_time={self.game_time}ms>'

    @validates('game_time')
    def validate_game_time(self, key, value):
        if value is not None and not isinstance(value, int):
            raise TypeError("game_time must be an integer (milliseconds) or None")
        return value
    
    @staticmethod
    def calc_replay_start_time(replay_end_time: int) -> int:
        """Calculate replay_start_time from replay_end_time (10s before, min 0)."""
        return max(0, replay_end_time - 10000)

    @validates('replay_end_time')
    def validate_replay_end_time(self, key, value):
        if value is not None and not isinstance(value, int):
            raise TypeError("replay_end_time must be an integer (milliseconds)")
        return value

    @validates('video_path')
    def validate_video_path(self, key, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("video_path must be a string")
        return value
    
    @validates('color')
    def validate_color(self, key, value):
        if value is None:
            return '#FFFFFF'
        if not isinstance(value, str) or not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise ValueError("color must be a 7-character hex string, e.g. '#ff0000'")
        return value.lower()

    @validates('comment')
    def validate_comment(self, key, value):
        if value is not None and not isinstance(value, str):
            raise TypeError('comment must be a string or None')
        return value or None   # treat empty string as None

    @validates('event_place')
    def validate_event_place(self, key, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("event_place must be a string or None")
        return value

    @property
    def game_time_seconds(self):
        return int(self.game_time) if self.game_time else 0

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
            'id':                  self.id,
            'game_id':             self.game_id,
            'event_id':            self.event_id,
            'event_name':          self.event.name         if self.event  else None,
            'event_short_name':    self.event.short_name   if self.event  else None,
            'event_image_path':    self.event.image_path   if self.event  else None,
            'event_color':         self.event.color        if self.event  else '#FFFFFF',
            'filter_class':        self.event.filter_class,
            'is_reported':         self.event.is_reported,
            'player_from_opponent':self.event.player_from_opponent,
            'period_id':           self.period_id,
            'period_description':  self.period.description if self.period else None,
            'team_id':             self.team_id,
            'team_name':           self.team.name          if self.team   else None,
            'team_short_name':     self.team.short_name    if self.team   else None,
            'team_name_14':        self.team.name_14    if self.team   else None,
            'player_id':           self.player_id,
            'player_number':       self.player.number      if self.player else None,
            'player_name':         self.player.full_name   if self.player else None,
            'game_time':           self.game_time,
            'game_time_seconds':   self.game_time_seconds,
            'game_time_formatted': self.game_time_formatted,
            'home_team_goals':     self.home_team_goals,
            'away_team_goals':     self.away_team_goals,
            'event_place':         self.event_place,
            'replay_start_time':   self.replay_start_time,
            'replay_end_time':     self.replay_end_time,
            'video_path':          self.video_path,
            'has_camera_data':     self.has_camera_data,
            'event_cameras':       [gc.to_dict() for gc in self.event_cameras],
            'is_visible':          self.is_visible,
            'created_at':          self.created_at.isoformat() if self.created_at else None,
            'updated_at':          self.updated_at.isoformat() if self.updated_at else None,
        }

def get_game_event_model():
    """Zwraca klasę GameEvent zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_events'
                and issubclass(cls, BaseGameEventMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy GameEvent w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
