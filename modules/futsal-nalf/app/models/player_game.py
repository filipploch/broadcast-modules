"""PlayerGame model - Association between Player and Game"""
from app.extensions import db
from datetime import datetime


class PlayerGame(db.Model):
    """
    Association between Player and Game (player participation in a game)
    
    Historical snapshot: is_goalkeeper, is_captain, number are copied from Player
    at time of assignment to preserve historical data if player changes team/role.
    """
    __tablename__ = 'player_games'

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False, index=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)
    
    # Player attributes in this game (copied from Player at time of assignment)
    # These are snapshots to preserve historical data if player changes team/role
    is_goalkeeper = db.Column(db.Boolean, default=False, nullable=False)
    is_captain = db.Column(db.Boolean, default=False, nullable=False)
    number = db.Column(db.Integer, nullable=True)  # Jersey number
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: player can only be assigned once per game
    __table_args__ = (
        db.UniqueConstraint('player_id', 'game_id', name='unique_player_game'),
    )

    def __repr__(self):
        return f'<PlayerGame player_id={self.player_id} game_id={self.game_id} team_id={self.team_id}>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'player_id': self.player_id,
            'player_name': self.player.full_name if self.player else None,
            'game_id': self.game_id,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'is_goalkeeper': self.is_goalkeeper,
            'is_captain': self.is_captain,
            'number': self.number,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
