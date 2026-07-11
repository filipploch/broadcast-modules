"""BaseLeagueForeignIdMixin — mapowanie lokalnego League.id na foreign_id konkretnego scrapera."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseLeagueForeignIdMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False, index=True)

    @declared_attr
    def league_id(cls):
        return db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False, index=True)

    foreign_id = db.Column(db.String(500), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    @declared_attr
    def league(cls):
        return db.relationship('League', backref=db.backref('foreign_ids', lazy='dynamic', cascade='all, delete-orphan'))

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('scraper_id', 'league_id', name='uix_league_foreign_id_scraper_league'),
            db.UniqueConstraint('scraper_id', 'foreign_id', name='uix_league_foreign_id_scraper_foreign'),
        )

    def __repr__(self):
        return f'<LeagueForeignId league_id={self.league_id} scraper_id={self.scraper_id} foreign_id={self.foreign_id}>'

    def to_dict(self):
        return {
            'id':           self.id,
            'scraper_id':   self.scraper_id,
            'scraper_name': self.scraper.name if self.scraper else None,
            'league_id':    self.league_id,
            'foreign_id':   self.foreign_id,
        }

    @classmethod
    def get_local_id(cls, scraper_id, foreign_id):
        row = cls.query.filter_by(scraper_id=scraper_id, foreign_id=foreign_id).first()
        return row.league_id if row else None

    @classmethod
    def get_foreign_id(cls, scraper_id, league_id):
        row = cls.query.filter_by(scraper_id=scraper_id, league_id=league_id).first()
        return row.foreign_id if row else None

    @classmethod
    def set_foreign_id(cls, scraper_id, league_id, foreign_id):
        """Utwórz lub zaktualizuj mapowanie (scraper, league) -> foreign_id."""
        row = cls.query.filter_by(scraper_id=scraper_id, league_id=league_id).first()
        if row:
            row.foreign_id = foreign_id
            row.updated_at = datetime.utcnow()
        else:
            row = cls(scraper_id=scraper_id, league_id=league_id, foreign_id=foreign_id)
            db.session.add(row)
        db.session.commit()
        return row


def get_league_foreign_id_model():
    """Zwraca konkretną klasę BaseLeagueForeignIdMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'league_foreign_ids'
                and issubclass(cls, BaseLeagueForeignIdMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseLeagueForeignIdMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_league_foreign_id_model()."
    )
