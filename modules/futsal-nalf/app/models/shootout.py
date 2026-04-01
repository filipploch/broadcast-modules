"""Shootout model - Penalty shootout results"""
from app.extensions import db
from datetime import datetime


class Shootout(db.Model):
    """Penalty shootout (konkurs rzutów karnych)"""
    __tablename__ = 'shootouts'

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key - one penalty shootout per game
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, unique=True, index=True)
    
    # Penalty shootout results (only goals, no time or fouls)
    home_team_shootouts = db.Column(db.Integer, default=0, nullable=False)
    away_team_shootouts = db.Column(db.Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Shootout for game_id={self.game_id}: {self.home_team_shootouts}:{self.away_team_shootouts}>'

    @property
    def winner_id(self):
        """Get winner team ID from penalty shootout"""
        if self.home_team_shootouts > self.away_team_shootouts:
            return self.game.home_team_id if self.game else None
        elif self.away_team_shootouts > self.home_team_shootouts:
            return self.game.away_team_id if self.game else None
        return None  # Draw (shouldn't happen in penalty shootout)

    @property
    def score_string(self):
        """Get formatted penalty score string"""
        return f"{self.home_team_shootouts}:{self.away_team_shootouts}"

    def update_score(self, home_shootouts, away_shootouts):
        """Update penalty shootout score"""
        self.home_team_shootouts = home_shootouts
        self.away_team_shootouts = away_shootouts
        self.updated_at = datetime.utcnow()

    def increment_home_shootouts(self):
        """Increment home team penalty goals"""
        self.home_team_shootouts += 1
        self.updated_at = datetime.utcnow()

    def increment_away_shootouts(self):
        """Increment away team penalty goals"""
        self.away_team_shootouts += 1
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'home_team_shootouts': self.home_team_shootouts,
            'away_team_shootouts': self.away_team_shootouts,
            'score_string': self.score_string,
            'winner_id': self.winner_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }