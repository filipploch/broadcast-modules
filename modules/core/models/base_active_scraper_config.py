"""BaseActiveScraperConfigMixin — który scraper obsługuje dany typ danych.

Jeden wiersz na typ danych (game/team/player/league/season), z FK do scrapers.id.
Zastępuje pomysł trzymania tego jako JSON w Settings — dzięki realnemu FK nie da się
wskazać nieistniejącego scrapera, a dodanie nowego typu danych to insert, nie migracja.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseActiveScraperConfigMixin:

    TYPE_GAME   = 'game'
    TYPE_TEAM   = 'team'
    TYPE_PLAYER = 'player'
    TYPE_LEAGUE = 'league'
    TYPE_SEASON = 'season'
    ALL_TYPES   = (TYPE_GAME, TYPE_TEAM, TYPE_PLAYER, TYPE_LEAGUE, TYPE_SEASON)

    id        = db.Column(db.Integer, primary_key=True)
    data_type = db.Column(db.String(20), nullable=False, unique=True, index=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False)

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ActiveScraperConfig {self.data_type} -> scraper_id={self.scraper_id}>'

    def to_dict(self):
        return {
            'id':           self.id,
            'data_type':    self.data_type,
            'scraper_id':   self.scraper_id,
            'scraper_name': self.scraper.name if self.scraper else None,
        }

    @classmethod
    def get_active_scraper(cls, data_type):
        """Zwraca obiekt Scraper aktywny dla danego typu danych, albo None."""
        row = cls.query.filter_by(data_type=data_type).first()
        return row.scraper if row else None

    @classmethod
    def get_active_scraper_id(cls, data_type):
        row = cls.query.filter_by(data_type=data_type).first()
        return row.scraper_id if row else None

    @classmethod
    def set_active_scraper(cls, data_type, scraper_id):
        """Utwórz lub zaktualizuj przypisanie scrapera dla typu danych."""
        row = cls.query.filter_by(data_type=data_type).first()
        if row:
            row.scraper_id = scraper_id
            row.updated_at = datetime.utcnow()
        else:
            row = cls(data_type=data_type, scraper_id=scraper_id)
            db.session.add(row)
        db.session.commit()
        return row

    @classmethod
    def get_all(cls):
        """Zwraca {data_type: scraper_id} dla wszystkich skonfigurowanych typów."""
        return {row.data_type: row.scraper_id for row in cls.query.all()}


def get_active_scraper_config_model():
    """Zwraca konkretną klasę BaseActiveScraperConfigMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'active_scraper_configs'
                and issubclass(cls, BaseActiveScraperConfigMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseActiveScraperConfigMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_active_scraper_config_model()."
    )
