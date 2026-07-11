"""BaseGameForeignIdMixin — mapowanie lokalnego Game.id na foreign_id konkretnego scrapera."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseGameForeignIdMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False, index=True)

    @declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)

    foreign_id = db.Column(db.String(500), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    @declared_attr
    def game(cls):
        return db.relationship('Game', backref=db.backref('foreign_ids', lazy='dynamic', cascade='all, delete-orphan'))

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('scraper_id', 'game_id', name='uix_game_foreign_id_scraper_game'),
            db.UniqueConstraint('scraper_id', 'foreign_id', name='uix_game_foreign_id_scraper_foreign'),
        )

    def __repr__(self):
        return f'<GameForeignId game_id={self.game_id} scraper_id={self.scraper_id} foreign_id={self.foreign_id}>'

    def to_dict(self):
        return {
            'id':           self.id,
            'scraper_id':   self.scraper_id,
            'scraper_name': self.scraper.name if self.scraper else None,
            'game_id':      self.game_id,
            'foreign_id':   self.foreign_id,
        }

    @classmethod
    def get_local_id(cls, scraper_id, foreign_id):
        row = cls.query.filter_by(scraper_id=scraper_id, foreign_id=foreign_id).first()
        return row.game_id if row else None

    @classmethod
    def get_foreign_id(cls, scraper_id, game_id):
        row = cls.query.filter_by(scraper_id=scraper_id, game_id=game_id).first()
        return row.foreign_id if row else None

    @classmethod
    def set_foreign_id(cls, scraper_id, game_id, foreign_id):
        """Utwórz/zaktualizuj mapowanie (scraper, game) -> foreign_id. Puste foreign_id usuwa mapowanie."""
        row = cls.query.filter_by(scraper_id=scraper_id, game_id=game_id).first()
        if foreign_id:
            if row:
                row.foreign_id = foreign_id
                row.updated_at = datetime.utcnow()
            else:
                row = cls(scraper_id=scraper_id, game_id=game_id, foreign_id=foreign_id)
                db.session.add(row)
        elif row:
            db.session.delete(row)
            row = None
        db.session.commit()
        return row


def get_game_foreign_id_model():
    """Zwraca konkretną klasę BaseGameForeignIdMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_foreign_ids'
                and issubclass(cls, BaseGameForeignIdMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseGameForeignIdMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_game_foreign_id_model()."
    )
