"""BaseLeagueScraperUrlMixin — adresy URL (i inne parametry) scrapowania ligi, per scraper.

Zastępuje sztywne kolumny games_url/table_url/scorers_url/assists_url/canadian_url
na League — różne scrapery danego modułu mogą potrzebować różnych adresów dla tej
samej ligi (np. malopolskizpn i superscore w garbarnia scrapują tę samą ligę
z różnych stron). Jeden wiersz = jeden typ URL dla jednej pary (liga, scraper).
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseLeagueScraperUrlMixin:

    URL_GAMES    = 'games_url'
    URL_TABLE    = 'table_url'
    URL_SCORERS  = 'scorers_url'
    URL_ASSISTS  = 'assists_url'
    URL_CANADIAN = 'canadian_url'
    ALL_URL_TYPES = (URL_GAMES, URL_TABLE, URL_SCORERS, URL_ASSISTS, URL_CANADIAN)

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False, index=True)

    @declared_attr
    def league_id(cls):
        return db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False, index=True)

    url_type = db.Column(db.String(20), nullable=False)
    url      = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    @declared_attr
    def league(cls):
        return db.relationship('League', backref=db.backref('scraper_urls', lazy='dynamic', cascade='all, delete-orphan'))

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('scraper_id', 'league_id', 'url_type', name='uix_league_scraper_url_scraper_league_type'),
        )

    def __repr__(self):
        return f'<LeagueScraperUrl league_id={self.league_id} scraper_id={self.scraper_id} {self.url_type}={self.url}>'

    def to_dict(self):
        return {
            'id':           self.id,
            'scraper_id':   self.scraper_id,
            'scraper_name': self.scraper.name if self.scraper else None,
            'league_id':    self.league_id,
            'url_type':     self.url_type,
            'url':          self.url,
        }

    @classmethod
    def get_url(cls, scraper_id, league_id, url_type):
        row = cls.query.filter_by(scraper_id=scraper_id, league_id=league_id, url_type=url_type).first()
        return row.url if row else None

    @classmethod
    def set_url(cls, scraper_id, league_id, url_type, url):
        """Utwórz/zaktualizuj URL. Pusty url usuwa istniejący wiersz (pole opcjonalne)."""
        row = cls.query.filter_by(scraper_id=scraper_id, league_id=league_id, url_type=url_type).first()
        if url:
            if row:
                row.url = url
                row.updated_at = datetime.utcnow()
            else:
                row = cls(scraper_id=scraper_id, league_id=league_id, url_type=url_type, url=url)
                db.session.add(row)
        elif row:
            db.session.delete(row)
            row = None
        db.session.commit()
        return row

    @classmethod
    def get_urls_for_league(cls, scraper_id, league_id):
        """Zwraca {url_type: url|None} dla wszystkich znanych typów URL danego scrapera/ligi."""
        rows = cls.query.filter_by(scraper_id=scraper_id, league_id=league_id).all()
        result = {url_type: None for url_type in cls.ALL_URL_TYPES}
        for row in rows:
            result[row.url_type] = row.url
        return result


def get_league_scraper_url_model():
    """Zwraca konkretną klasę BaseLeagueScraperUrlMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'league_scraper_urls'
                and issubclass(cls, BaseLeagueScraperUrlMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseLeagueScraperUrlMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_league_scraper_url_model()."
    )
