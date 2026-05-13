"""Season model - Football seasons"""
from core.extensions import db
from datetime import datetime
from core.models.base_league import BaseLeagueMixin
from sqlalchemy.orm import declared_attr

def _get_season():
    from core.models.base_season import get_season_model
    return get_season_model()

def _get_game():
    from core.models.base_game import get_game_model
    return get_game_model()

def _get_league():
    from core.models.base_league import get_league_model
    return get_league_model()

def _get_settings():
    from core.models.base_settings import get_settings_model
    return get_settings_model()




class BaseSeasonMixin:
    """Football season (e.g., Jesień 2025)"""

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    foreign_id = db.Column(db.String(500), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    @declared_attr
    def leagues(cls):
        return db.relationship('League', backref='season', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Season {self.number}: {self.name}>'

    @property
    def total_leagues(self):
        """Get total number of leagues in this season"""
        return self.leagues.count()

    @property
    def total_games(self):
        """Get total number of games in this season"""
        League = _get_league()
        from core.models.base_game import BaseGameMixin
        return _get_game().query.join(League).filter(League.season_id == self.id).count()
    
    @property
    def set_newest_season_as_current():
        Season = _get_season()
        newest_season = Season.query.order_by(Season.number.desc()).first()
        Settings = _get_settings()
        Settings.set_current_season(newest_season.id)

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

def get_season_model():
    """Zwraca klasę Season zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'seasons'
                and issubclass(cls, BaseSeasonMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Season w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
