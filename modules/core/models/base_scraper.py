"""BaseScraperMixin — abstrakcyjna klasa bazowa dla rejestru scraperów danego modułu.

Każdy wiersz odpowiada jednemu folderowi w app/managers/scrapers/<folder>/
(np. 'nalffutsal', 'malopolskizpn', 'laczynaspilka', 'superscore').
"""
from core.extensions import db
from datetime import datetime


class BaseScraperMixin:

    id     = db.Column(db.Integer, primary_key=True)
    name   = db.Column(db.String(100), nullable=False, unique=True)
    folder = db.Column(db.String(100), nullable=False, unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Scraper {self.name}>'

    def to_dict(self):
        return {
            'id':     self.id,
            'name':   self.name,
            'folder': self.folder,
        }

    @classmethod
    def get_by_folder(cls, folder):
        """Znajdź scraper po nazwie folderu (np. 'laczynaspilka')."""
        return cls.query.filter_by(folder=folder).first()


def get_scraper_model():
    """Zwraca konkretną klasę BaseScraperMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'scrapers'
                and issubclass(cls, BaseScraperMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseScraperMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_scraper_model()."
    )
