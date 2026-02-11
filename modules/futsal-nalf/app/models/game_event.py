"""GameEvent model - Events occurring during a game"""
from app.extensions import db
from datetime import datetime


class GameEvent(db.Model):
    """Game event (occurrence of an event type during a game)"""
    __tablename__ = 'game_events'

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False, index=True)
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=False, index=True)  # Current period when event occurred
    
    # Optional: team and player (only if Event.is_reported = True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True, index=True)
    
    # Time when event occurred (milliseconds from timer plugin)
    time = db.Column(db.Integer, nullable=False)  # Time in milliseconds
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for common queries
    __table_args__ = (
        db.Index('ix_game_event_game_time', 'game_id', 'time'),
        db.Index('ix_game_event_period', 'period_id', 'time'),
    )

    def __repr__(self):
        return f'<GameEvent game_id={self.game_id} event_id={self.event_id} time={self.time}ms>'

    @property
    def time_seconds(self):
        """Get time in seconds"""
        return self.time / 1000 if self.time else 0

    @property
    def time_formatted(self):
        """Get formatted time as MM:SS"""
        seconds = int(self.time_seconds)
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02d}:{secs:02d}"

    def to_dict(self):
        """Convert to dictionary"""
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
            'time': self.time,
            'time_seconds': self.time_seconds,
            'time_formatted': self.time_formatted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
