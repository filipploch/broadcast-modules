"""BasePendingPlayerMatchMixin — kandydaci do dopasowania zawodników wykrytych
przez scraper kadry drużyny, oczekujący na potwierdzenie przez człowieka.

Analogiczne do BasePendingTeamMatchMixin, ale kluczowane przez team_id
(zawodnik należy do jednej drużyny — bez odpowiednika członkostwa w lidze)
zamiast league_id, i sugeruje suggested_player_id zamiast suggested_team_id.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BasePendingPlayerMatchMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False, index=True)

    scraped_first_name    = db.Column(db.String(100), nullable=False)
    scraped_last_name     = db.Column(db.String(100), nullable=False)
    scraped_foreign_id    = db.Column(db.String(500), nullable=False)
    scraped_is_goalkeeper = db.Column(db.Boolean, default=False, nullable=False)

    @declared_attr
    def suggested_player_id(cls):
        return db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)

    similarity_score = db.Column(db.Float, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def team(cls):
        return db.relationship('Team')

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    @declared_attr
    def suggested_player(cls):
        return db.relationship('Player')

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('scraper_id', 'team_id', 'scraped_foreign_id',
                                 name='uix_pending_player_match_scraper_team_foreign'),
        )

    def __repr__(self):
        return f'<PendingPlayerMatch team_id={self.team_id} scraper_id={self.scraper_id} {self.scraped_last_name!r} {self.scraped_first_name!r}>'

    def to_dict(self):
        return {
            'id':                   self.id,
            'team_id':              self.team_id,
            'scraper_id':           self.scraper_id,
            'scraped_first_name':   self.scraped_first_name,
            'scraped_last_name':    self.scraped_last_name,
            'scraped_foreign_id':   self.scraped_foreign_id,
            'scraped_is_goalkeeper': self.scraped_is_goalkeeper,
            'suggested_player_id':  self.suggested_player_id,
            'suggested_player_name': self.suggested_player.full_name if self.suggested_player else None,
            'suggested_player_team_name': self.suggested_player.team.name if self.suggested_player and self.suggested_player.team else None,
            'similarity_score':     self.similarity_score,
        }

    @classmethod
    def upsert(cls, team_id, scraper_id, scraped_first_name, scraped_last_name, scraped_foreign_id,
               scraped_is_goalkeeper=False, suggested_player_id=None, similarity_score=None):
        """Utwórz albo odśwież (przy ponownym scrapowaniu) wiersz oczekujący."""
        row = cls.query.filter_by(
            scraper_id=scraper_id, team_id=team_id, scraped_foreign_id=scraped_foreign_id
        ).first()
        if row:
            row.scraped_first_name = scraped_first_name
            row.scraped_last_name = scraped_last_name
            row.scraped_is_goalkeeper = scraped_is_goalkeeper
            row.suggested_player_id = suggested_player_id
            row.similarity_score = similarity_score
            row.updated_at = datetime.utcnow()
        else:
            row = cls(
                team_id=team_id, scraper_id=scraper_id,
                scraped_first_name=scraped_first_name, scraped_last_name=scraped_last_name,
                scraped_foreign_id=scraped_foreign_id, scraped_is_goalkeeper=scraped_is_goalkeeper,
                suggested_player_id=suggested_player_id, similarity_score=similarity_score,
            )
            db.session.add(row)
        db.session.commit()
        return row

    @classmethod
    def get_for_team(cls, team_id, scraper_id=None):
        query = cls.query.filter_by(team_id=team_id)
        if scraper_id is not None:
            query = query.filter_by(scraper_id=scraper_id)
        return query.order_by(cls.scraped_last_name, cls.scraped_first_name).all()


def get_pending_player_match_model():
    """Zwraca konkretną klasę BasePendingPlayerMatchMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'pending_player_matches'
                and issubclass(cls, BasePendingPlayerMatchMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BasePendingPlayerMatchMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_pending_player_match_model()."
    )
