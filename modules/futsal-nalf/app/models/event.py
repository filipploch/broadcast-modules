"""Event model - Game event types"""
from app.extensions import db
from datetime import datetime


class Event(db.Model):
    """Game event type (goal, foul, card, etc.)"""
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    
    # Event info
    name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(50), nullable=False)
    
    # Whether this event is reported (assigned to team/player)
    # True = events like goals, cards (need team/player assignment)
    # False = events like period start/end (no team/player)
    is_reported = db.Column(db.Boolean, default=False, nullable=False)
    
    # Optional image for UI
    image_path = db.Column(db.String(500), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    game_events = db.relationship('GameEvent', backref='event', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Event {self.name} (reported: {self.is_reported})>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'short_name': self.short_name,
            'is_reported': self.is_reported,
            'image_path': self.image_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
