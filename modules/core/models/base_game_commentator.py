"""GameCommentator model - Association between Game and Commentator"""
from core.extensions import db
from datetime import datetime


class BaseGameCommentatorMixin:
    """Association between Game and Commentator (commentator assignment to game)"""

    # Predefined commentator types
    TYPE_MAIN = "Główny"
    TYPE_ASSISTANT = "Asystent"
    
    REFEREE_TYPES = [TYPE_MAIN, TYPE_ASSISTANT]

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    commentator_id = db.Column(db.Integer, db.ForeignKey('commentators.id'), nullable=False, index=True)
    
    # Commentator type (Główny, Asystent)
    type = db.Column(db.String(50), nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: commentator can only be assigned once per game
    @db.declared_attr
    def __table_args__(cls):
        return (
        db.UniqueConstraint('game_id', 'commentator_id', name='unique_game_commentator')
,
    )

    def __repr__(self):
        return f'<GameCommentator game_id={self.game_id} commentator_id={self.commentator_id} type={self.type}>'

    @classmethod
    def is_valid_type(cls, commentator_type):
        """Check if commentator type is valid"""
        return commentator_type in cls.REFEREE_TYPES

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'commentator_id': self.commentator_id,
            'name': self.commentator.full_name if self.commentator else None,
            'type': self.type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

def get_game_commentator_model():
    """Zwraca klasę GameCommentator zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_commentators'
                and issubclass(cls, BaseGameCommentatorMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy GameCommentator w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
