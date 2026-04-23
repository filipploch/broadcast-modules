"""Event model - Game event types"""
import re
from sqlalchemy.orm import validates, declared_attr
from core.extensions import db
from datetime import datetime


class BaseEventMixin:
    """Game event type (goal, foul, card, etc.)"""

    id = db.Column(db.Integer, primary_key=True)
    
    # Event info
    name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(50), nullable=False)
    
    # Whether this event is reported (assigned to team/player)
    # True = events like goals, cards (need team/player assignment)
    # False = events like period start/end (no team/player)
    is_reported = db.Column(db.Boolean, default=False, nullable=False)

     # Display colour for UI/overlay (hex, e.g. '#e53935')
    color = db.Column(db.String(7), nullable=False, default='#FFFFFF')

    # Filter class for grouping event types (e.g. 'goal' for both goal and own-goal)
    # None = event is not displayed in filtered views
    filter_class = db.Column(db.String(50), nullable=True)

    # True = player is assigned from the opposing team (e.g. own goal)
    player_from_opponent = db.Column(db.Boolean, nullable=False, default=False)
    
    # Optional image for UI
    image_path = db.Column(db.String(500), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    @declared_attr
    def game_events(cls):
        return db.relationship('GameEvent', backref='event', lazy='dynamic', cascade='all, delete-orphan')

    @validates('color')
    def validate_color(self, key, value):
        if value is None:
            return '#FFFFFF'
        if not isinstance(value, str) or not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise ValueError("color must be a 7-character hex string, e.g. '#ff0000'")
        return value.lower()

    def __repr__(self):
        return f'<Event {self.name} (reported: {self.is_reported})>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'short_name': self.short_name,
            'is_reported': self.is_reported,
            'color': self.color,
            'filter_class': self.filter_class,
            'player_from_opponent': self.player_from_opponent,
            'image_path': self.image_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

def get_event_model():
    """Zwraca klasę Event zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'events'
                and issubclass(cls, BaseEventMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Event w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
