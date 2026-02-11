"""Season model - Football seasons"""
from app.extensions import db
from datetime import datetime
from app.models.league import League


class Season(db.Model):
    """Football season (e.g., Jesień 2025)"""
    __tablename__ = 'seasons'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    foreign_id = db.Column(db.String(500), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    leagues = db.relationship('League', backref='season', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Season {self.number}: {self.name}>'

    @property
    def total_leagues(self):
        """Get total number of leagues in this season"""
        return self.leagues.count()

    @property
    def total_games(self):
        """Get total number of games in this season"""
        from app.models.game import Game
        return Game.query.join(League).filter(League.season_id == self.id).count()

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'number': self.number,
            'name': self.name,
            'foreign_id': self.foreign_id,
            'total_leagues': self.total_leagues,
            'total_games': self.total_games,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }