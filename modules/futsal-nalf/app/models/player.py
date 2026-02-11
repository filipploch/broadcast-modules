"""Player model - Football players"""
from app.extensions import db
from datetime import datetime


class Player(db.Model):
    """Football player"""
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    foreign_id = db.Column(db.String(500), nullable=True)
    
    # Player info
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    number = db.Column(db.Integer, nullable=True)  # Jersey number
    
    # Team relationship
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)
    
    # Player attributes
    is_goalkeeper = db.Column(db.Boolean, default=False, nullable=False)
    is_captain = db.Column(db.Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    player_games = db.relationship('PlayerGame', backref='player', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Player {self.first_name} {self.last_name} (Team: {self.team_id})>'

    @property
    def full_name(self):
        """Get full name"""
        return f"{self.first_name} {self.last_name}"

    @property
    def short_name(self):
        """Get short name (first letter of first name + last name)"""
        return f"{self.first_name[0]}. {self.last_name}" if self.first_name else self.last_name

    @property
    def display_name(self):
        """Get display name with captain/goalkeeper indicators"""
        name = self.full_name
        indicators = []
        
        if self.is_captain:
            indicators.append("(C)")
        if self.is_goalkeeper:
            indicators.append("(GK)")
        
        if indicators:
            name += " " + " ".join(indicators)
        
        return name

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'foreign_id': self.foreign_id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'number': self.number,
            'full_name': self.full_name,
            'short_name': self.short_name,
            'display_name': self.display_name,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'is_goalkeeper': self.is_goalkeeper,
            'is_captain': self.is_captain,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
