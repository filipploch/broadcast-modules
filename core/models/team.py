"""Team model - Football teams"""
from core.extensions import db
from datetime import datetime
import json


class Team(db.Model):
    """Football team"""
    __tablename__ = 'teams'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name_14 = db.Column(db.String(14), nullable=False)  # Shortened name (max 14 chars)
    short_name = db.Column(db.String(3), nullable=False, index=True)  # 3-letter abbreviation
    team_url = db.Column(db.String(500), nullable=False)
    logo_path = db.Column(db.String(500), default='static/images/logos/default.png')
    foreign_id = db.Column(db.String(500), nullable=True)
    uniform = db.Column(db.Text, nullable=True)  # JSON: {"home": ["#111111", ...], "away": ["#222222", ...]}

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    league_participations = db.relationship('LeagueTeam', backref='team', lazy='dynamic', cascade='all, delete-orphan')
    home_games = db.relationship('Game', foreign_keys='Game.home_team_id', backref='home_team', lazy='dynamic')
    away_games = db.relationship('Game', foreign_keys='Game.away_team_id', backref='away_team', lazy='dynamic')
    players = db.relationship('Player', backref='team', lazy='dynamic', cascade='all, delete-orphan')
    game_players = db.relationship('GamePlayer', backref='team', lazy='dynamic')
    game_events = db.relationship('GameEvent', backref='team', lazy='dynamic')


    def __repr__(self):
        return f'<Team {self.short_name}: {self.name}>'

    def get_uniform(self):
        """Return uniform colors as dict, or empty structure if not set"""
        if not self.uniform:
            return {"home": [], "away": []}
        try:
            return json.loads(self.uniform)
        except (json.JSONDecodeError, TypeError):
            return {"home": [], "away": []}

    def set_uniform(self, home_colors: list, away_colors: list):
        """Set uniform colors from lists of hex strings"""
        self.uniform = json.dumps({"home": home_colors, "away": away_colors})

    def get_leagues(self, season_id=None):
        """Get leagues this team participates in"""
        query = self.league_participations
        if season_id:
            from core.models.league import League
            query = query.join(League).filter(League.season_id == season_id)
        return query.all()

    def get_games(self, league_id=None):
        """Get all games for this team (home and away)"""
        from core.models.game import Game

        home_query = Game.query.filter(Game.home_team_id == self.id)
        away_query = Game.query.filter(Game.away_team_id == self.id)

        if league_id:
            home_query = home_query.filter(Game.league_id == league_id)
            away_query = away_query.filter(Game.league_id == league_id)

        return home_query.union(away_query).order_by(Game.date).all()

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'name_14': self.name_14,
            'short_name': self.short_name,
            'team_url': self.team_url,
            'logo_path': self.logo_path,
            'foreign_id': self.foreign_id,
            'uniform': self.get_uniform(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }