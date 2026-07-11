"""BaseTeamForeignIdMixin — mapowanie lokalnego Team.id na foreign_id konkretnego scrapera.

Jedna drużyna może mieć różne identyfikatory w różnych źródłach (np. UUID
w laczynaspilka i nazwę używaną do dopasowania w superscore) — stąd osobny
wiersz na parę (scraper, team), a nie kolumna na Team.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseTeamForeignIdMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False, index=True)

    @declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)

    foreign_id = db.Column(db.String(500), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    @declared_attr
    def team(cls):
        return db.relationship('Team', backref=db.backref('foreign_ids', lazy='dynamic', cascade='all, delete-orphan'))

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('scraper_id', 'team_id', name='uix_team_foreign_id_scraper_team'),
            db.UniqueConstraint('scraper_id', 'foreign_id', name='uix_team_foreign_id_scraper_foreign'),
        )

    def __repr__(self):
        return f'<TeamForeignId team_id={self.team_id} scraper_id={self.scraper_id} foreign_id={self.foreign_id}>'

    def to_dict(self):
        return {
            'id':           self.id,
            'scraper_id':   self.scraper_id,
            'scraper_name': self.scraper.name if self.scraper else None,
            'team_id':      self.team_id,
            'foreign_id':   self.foreign_id,
        }

    @classmethod
    def get_local_id(cls, scraper_id, foreign_id):
        row = cls.query.filter_by(scraper_id=scraper_id, foreign_id=foreign_id).first()
        return row.team_id if row else None

    @classmethod
    def get_foreign_id(cls, scraper_id, team_id):
        row = cls.query.filter_by(scraper_id=scraper_id, team_id=team_id).first()
        return row.foreign_id if row else None

    @classmethod
    def set_foreign_id(cls, scraper_id, team_id, foreign_id):
        """Utwórz/zaktualizuj mapowanie (scraper, team) -> foreign_id. Puste foreign_id usuwa mapowanie."""
        row = cls.query.filter_by(scraper_id=scraper_id, team_id=team_id).first()
        if foreign_id:
            if row:
                row.foreign_id = foreign_id
                row.updated_at = datetime.utcnow()
            else:
                row = cls(scraper_id=scraper_id, team_id=team_id, foreign_id=foreign_id)
                db.session.add(row)
        elif row:
            db.session.delete(row)
            row = None
        db.session.commit()
        return row


def get_team_foreign_id_model():
    """Zwraca konkretną klasę BaseTeamForeignIdMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'team_foreign_ids'
                and issubclass(cls, BaseTeamForeignIdMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseTeamForeignIdMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_team_foreign_id_model()."
    )
