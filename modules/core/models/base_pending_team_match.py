"""BasePendingTeamMatchMixin — kandydaci do dopasowania drużyn wykrytych przez
scraper drużyn ligi, oczekujący na potwierdzenie przez człowieka.

Scraper drużyn nigdy nie łączy automatycznie znalezionej drużyny z www z
rekordem Team w bazie — tylko proponuje najbardziej prawdopodobnego kandydata
(po podobieństwie nazw). Wiersz znika po zatwierdzeniu (Team.set_foreign_id +
ewentualne dopisanie do ligi) albo odrzuceniu.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BasePendingTeamMatchMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def league_id(cls):
        return db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False, index=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False, index=True)

    scraped_name       = db.Column(db.String(200), nullable=False)
    scraped_foreign_id = db.Column(db.String(500), nullable=False)

    @declared_attr
    def suggested_team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    similarity_score = db.Column(db.Float, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def league(cls):
        return db.relationship('League')

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    @declared_attr
    def suggested_team(cls):
        return db.relationship('Team')

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('scraper_id', 'league_id', 'scraped_foreign_id',
                                 name='uix_pending_team_match_scraper_league_foreign'),
        )

    def __repr__(self):
        return f'<PendingTeamMatch league_id={self.league_id} scraper_id={self.scraper_id} {self.scraped_name!r}>'

    def to_dict(self):
        return {
            'id':                  self.id,
            'league_id':           self.league_id,
            'scraper_id':          self.scraper_id,
            'scraped_name':        self.scraped_name,
            'scraped_foreign_id':  self.scraped_foreign_id,
            'suggested_team_id':   self.suggested_team_id,
            'suggested_team_name': self.suggested_team.name if self.suggested_team else None,
            'similarity_score':    self.similarity_score,
        }

    @classmethod
    def upsert(cls, league_id, scraper_id, scraped_name, scraped_foreign_id,
               suggested_team_id=None, similarity_score=None):
        """Utwórz albo odśwież (przy ponownym scrapowaniu) wiersz oczekujący."""
        row = cls.query.filter_by(
            scraper_id=scraper_id, league_id=league_id, scraped_foreign_id=scraped_foreign_id
        ).first()
        if row:
            row.scraped_name = scraped_name
            row.suggested_team_id = suggested_team_id
            row.similarity_score = similarity_score
            row.updated_at = datetime.utcnow()
        else:
            row = cls(
                league_id=league_id, scraper_id=scraper_id,
                scraped_name=scraped_name, scraped_foreign_id=scraped_foreign_id,
                suggested_team_id=suggested_team_id, similarity_score=similarity_score,
            )
            db.session.add(row)
        db.session.commit()
        return row

    @classmethod
    def get_for_league(cls, league_id, scraper_id=None):
        query = cls.query.filter_by(league_id=league_id)
        if scraper_id is not None:
            query = query.filter_by(scraper_id=scraper_id)
        return query.order_by(cls.scraped_name).all()


def get_pending_team_match_model():
    """Zwraca konkretną klasę BasePendingTeamMatchMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'pending_team_matches'
                and issubclass(cls, BasePendingTeamMatchMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BasePendingTeamMatchMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_pending_team_match_model()."
    )
