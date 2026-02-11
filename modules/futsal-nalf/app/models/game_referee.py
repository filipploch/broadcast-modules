"""GameReferee model - Association between Game and Referee"""
from app.extensions import db
from datetime import datetime


class GameReferee(db.Model):
    """Association between Game and Referee (referee assignment to game)"""
    __tablename__ = 'game_referees'

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
    __table_args__ = (
        db.UniqueConstraint('game_id', 'referee_id', name='unique_game_referee'),
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
            'referee_name': self.referee.full_name if self.referee else None,
            'type': self.type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
