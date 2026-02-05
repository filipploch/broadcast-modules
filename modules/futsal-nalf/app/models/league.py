"""League model - Football leagues"""
from app.extensions import db
from datetime import datetime


class League(db.Model):
    """Football league (e.g., Dywizja A, Dywizja B, Puchar Ligi)"""
    __tablename__ = 'leagues'

    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('seasons.id'), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)

    # URLs to external resources
    games_url = db.Column(db.String(500), nullable=False)
    table_url = db.Column(db.String(500), nullable=True)
    scorers_url = db.Column(db.String(500), nullable=False)
    assists_url = db.Column(db.String(500), nullable=False)
    canadian_url = db.Column(db.String(500), nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # season relationship defined in Season model (backref)
    teams = db.relationship('LeagueTeam', backref='league', lazy='dynamic', cascade='all, delete-orphan')
    games = db.relationship('Game', backref='league', lazy='dynamic', cascade='all, delete-orphan')

    # Composite unique constraint: season + name must be unique
    __table_args__ = (
        db.UniqueConstraint('season_id', 'name', name='uix_season_league'),
    )

    def __repr__(self):
        return f'<League {self.name} (Season {self.season_id})>'

    @property
    def total_teams(self):
        """Get total number of teams in this league"""
        return self.teams.count()

    @property
    def total_games(self):
        """Get total number of games in this league"""
        return self.games.count()

    def get_teams(self, group_nr=None):
        """Get teams in this league, optionally filtered by group"""
        query = self.teams
        if group_nr is not None:
            query = query.filter_by(group_nr=group_nr)
        return query.all()

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'season_id': self.season_id,
            'season_name': self.season.name if self.season else None,
            'name': self.name,
            'games_url': self.games_url,
            'table_url': self.table_url,
            'scorers_url': self.scorers_url,
            'assists_url': self.assists_url,
            'canadian_url': self.canadian_url,
            'total_teams': self.total_teams,
            'total_games': self.total_games,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }