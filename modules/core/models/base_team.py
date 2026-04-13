"""BaseTeam — abstrakcyjna klasa bazowa dla modeli drużyny we wszystkich modułach."""
from core.extensions import db
from datetime import datetime
import json

def _get_game():
    from core.models.base_game import get_game_model
    return get_game_model()



class BaseTeam(db.Model):
    """Football team"""
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name_14 = db.Column(db.String(14), nullable=False)  # Shortened name (max 14 chars)
    short_name = db.Column(db.String(3), nullable=False, index=True)  # 3-letter abbreviation
    logo_path = db.Column(db.String(500), default='static/images/logos/default.png')
    foreign_id = db.Column(db.String(500), nullable=True)
    uniform = db.Column(db.Text, nullable=True)  # JSON: {"home": ["#111111", ...], "away": ["#222222", ...]}

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    @db.declared_attr
    def league_participations(cls):
        return db.relationship('LeagueTeam', backref='team', lazy='dynamic', cascade='all, delete-orphan')
    @db.declared_attr
    def home_games(cls):
        return db.relationship('Game', foreign_keys='Game.home_team_id', backref='home_team', lazy='dynamic')
    @db.declared_attr
    def away_games(cls):
        return db.relationship('Game', foreign_keys='Game.away_team_id', backref='away_team', lazy='dynamic')
    @db.declared_attr
    def players(cls):
        return db.relationship('Player', backref='team', lazy='dynamic', cascade='all, delete-orphan')
    @db.declared_attr
    def game_players(cls):
        return db.relationship('GamePlayer', backref='team', lazy='dynamic')
    @db.declared_attr
    def game_events(cls):
        return db.relationship('GameEvent', backref='team', lazy='dynamic')


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
            from core.models.base_league import BaseLeague
            query = query.join(League).filter(League.season_id == season_id)
        return query.all()

    def get_games(self, league_id=None):
        """Get all games for this team (home and away)"""
        from core.models.base_game import BaseGame

        home_query = _get_game().query.filter(_get_game().home_team_id == self.id)
        away_query = _get_game().query.filter(_get_game().away_team_id == self.id)

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

def get_team_model():
    """Zwraca konkretną klasę BaseTeam zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'teams'
                and issubclass(cls, BaseTeam)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseTeam w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_team_model()."
    )