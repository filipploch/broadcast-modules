"""BaseLeagueMixin — abstrakcyjna klasa bazowa dla modeli ligi we wszystkich modułach."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseLeagueMixin:
    """Football league (e.g., Dywizja A, Dywizja B, Puchar Ligi)"""
    

    id = db.Column(db.Integer, primary_key=True)
    @declared_attr
    def season_id(cls):
        return db.Column(db.Integer, db.ForeignKey('seasons.id'), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    foreign_id = db.Column(db.String(500), nullable=True)

    # URLs to external resources

    # True  = liga grupowa (remis kończy mecz, brak rzutów karnych)
    # False = rozgrywki pucharowe (remis → konkurs rzutów karnych)
    allows_draw = db.Column(db.Boolean, nullable=False, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # season relationship defined in BaseSeasonMixin model (backref)
    @db.declared_attr
    def teams(cls):
        return db.relationship('LeagueTeam', backref='league', lazy='dynamic', cascade='all, delete-orphan')
    @db.declared_attr
    def games(cls):
        return db.relationship('Game', backref='league', lazy='dynamic', cascade='all, delete-orphan')

    # Composite unique constraint: season + name must be unique
    @db.declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('season_id', 'name', name='uix_season_league'),
        )

    def __repr__(self):
        return f'<League {self.name} (BaseSeasonMixin {self.season_id})>'

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
            'foreign_id': self.foreign_id,
            'games_url': self.games_url,
            'table_url': self.table_url,
            'scorers_url': self.scorers_url,
            'assists_url': self.assists_url,
            'canadian_url': self.canadian_url,
            'total_teams': self.total_teams,
            'allows_draw': self.allows_draw,
            'total_games': self.total_games,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

def get_league_model():
    """Zwraca konkretną klasę BaseLeagueMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'leagues'
                and issubclass(cls, BaseLeagueMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseLeagueMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_league_model()."
    )
