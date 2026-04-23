"""GameReferee model - Association between Game and Referee"""
from core.extensions import db
from datetime import datetime


class BaseGameRefereeMixin:
    """Association between Game and Referee (referee assignment to game)"""

    # Predefined referee types
    TYPE_MAIN = "Główny"
    TYPE_ASSISTANT = "Asystent"
    
    REFEREE_TYPES = [TYPE_MAIN, TYPE_ASSISTANT]

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    referee_id = db.Column(db.Integer, db.ForeignKey('referees.id'), nullable=False, index=True)
    
    # Referee type (Główny, Asystent)
    type = db.Column(db.String(50), nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: referee can only be assigned once per game
    @db.declared_attr
    def __table_args__(cls):
        return (
        db.UniqueConstraint('game_id', 'referee_id', name='unique_game_referee')
,
    )

    def __repr__(self):
        return f'<GameReferee game_id={self.game_id} referee_id={self.referee_id} type={self.type}>'

    @classmethod
    def is_valid_type(cls, referee_type):
        """Check if referee type is valid"""
        return referee_type in cls.REFEREE_TYPES

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'referee_id': self.referee_id,
            'name': self.referee.full_name if self.referee else None,
            'type': self.type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

def get_game_referee_model():
    """Zwraca klasę GameReferee zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_referees'
                and issubclass(cls, BaseGameRefereeMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy GameReferee w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
