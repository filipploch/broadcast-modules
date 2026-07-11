"""BaseLeagueMixin — abstrakcyjna klasa bazowa dla modeli ligi we wszystkich modułach."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr

def _get_league_foreign_id():
    from core.models.base_league_foreign_id import get_league_foreign_id_model
    return get_league_foreign_id_model()

def _get_league_scraper_url():
    from core.models.base_league_scraper_url import get_league_scraper_url_model
    return get_league_scraper_url_model()

def _get_scraper():
    from core.models.base_scraper import get_scraper_model
    return get_scraper_model()


class BaseLeagueMixin:
    """Football league (e.g., Dywizja A, Dywizja B, Puchar Ligi)"""


    id = db.Column(db.Integer, primary_key=True)
    @declared_attr
    def season_id(cls):
        return db.Column(db.Integer, db.ForeignKey('seasons.id'), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)

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

    def get_foreign_id(self, scraper_id):
        """Zwraca foreign_id tej ligi dla danego scrapera, albo None."""
        return _get_league_foreign_id().get_foreign_id(scraper_id, self.id)

    def set_foreign_id(self, scraper_id, foreign_id):
        """Zapisuje/aktualizuje foreign_id tej ligi dla danego scrapera."""
        return _get_league_foreign_id().set_foreign_id(scraper_id, self.id, foreign_id)

    def get_foreign_ids(self):
        """Zwraca {scraper.folder: foreign_id} dla wszystkich scraperów mapujących tę ligę."""
        return {row.scraper.folder: row.foreign_id for row in self.foreign_ids}

    def get_scraper_url(self, scraper_id, url_type):
        """Zwraca jeden URL (np. 'games_url') skonfigurowany dla danego scrapera, albo None."""
        return _get_league_scraper_url().get_url(scraper_id, self.id, url_type)

    def set_scraper_url(self, scraper_id, url_type, url):
        """Zapisuje/aktualizuje/usuwa (gdy url puste) jeden URL dla danego scrapera."""
        return _get_league_scraper_url().set_url(scraper_id, self.id, url_type, url)

    def get_scraper_urls(self, scraper_id):
        """Zwraca {url_type: url|None} dla wszystkich typów URL danego scrapera."""
        return _get_league_scraper_url().get_urls_for_league(scraper_id, self.id)

    def get_all_scraper_data(self):
        """Zwraca {scraper.folder: {url_type: url, ..., 'foreign_id': ...}} dla scraperów
        z jakimikolwiek danymi skonfigurowanymi dla tej ligi."""
        result = {}
        for scraper in _get_scraper().query.all():
            urls = self.get_scraper_urls(scraper.id)
            foreign_id = self.get_foreign_id(scraper.id)
            if any(urls.values()) or foreign_id:
                data = dict(urls)
                data['foreign_id'] = foreign_id
                result[scraper.folder] = data
        return result

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
            'foreign_ids': self.get_foreign_ids(),
            'scraper_data': self.get_all_scraper_data(),
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
