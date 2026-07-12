"""BasePendingPlayerDepartureMixin — zawodnicy, których scraper kadry drużyny
przestał widzieć w składzie na www, oczekujący na potwierdzenie odejścia
przez człowieka.

Kandydatem jest wyłącznie zawodnik, który ma już zapisany foreign_id dla
danego scrapera (czyli był wcześniej świadomie dopasowany przez admina) —
ręcznie dodani zawodnicy bez foreign_id nigdy nie są tu automatycznie
oznaczani, bo scraper nie ma o nich żadnej opinii.

Potwierdzenie NIE usuwa zawodnika — zeruje mu team_id (zostaje "wolnym
agentem", widoczny na liście zawodników bez drużyny). Historia meczowa
(GamePlayer) ma własny snapshot team_id z chwili meczu, więc nie jest tym
ruszana.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BasePendingPlayerDepartureMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False, index=True)

    @declared_attr
    def player_id(cls):
        return db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @declared_attr
    def team(cls):
        return db.relationship('Team')

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    @declared_attr
    def player(cls):
        return db.relationship('Player')

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('scraper_id', 'team_id', 'player_id',
                                 name='uix_pending_player_departure_scraper_team_player'),
        )

    def __repr__(self):
        return f'<PendingPlayerDeparture team_id={self.team_id} player_id={self.player_id}>'

    def to_dict(self):
        return {
            'id':          self.id,
            'team_id':     self.team_id,
            'scraper_id':  self.scraper_id,
            'player_id':   self.player_id,
            'player_name': self.player.full_name if self.player else None,
        }

    @classmethod
    def sync(cls, team_id, scraper_id, departed_player_ids):
        """
        Ujednolica kolejkę oczekujących odejść dla (team_id, scraper_id) ze
        świeżo wykrytym zbiorem departed_player_ids: dopisuje nowe, usuwa te,
        których zawodnik znów pojawił się w scrapowanym składzie (samo-naprawa,
        tak jak przy PendingTeamMatch/PendingPlayerMatch).
        """
        existing = cls.query.filter_by(team_id=team_id, scraper_id=scraper_id).all()
        existing_player_ids = {row.player_id for row in existing}

        for row in existing:
            if row.player_id not in departed_player_ids:
                db.session.delete(row)

        for player_id in departed_player_ids:
            if player_id not in existing_player_ids:
                db.session.add(cls(team_id=team_id, scraper_id=scraper_id, player_id=player_id))

        db.session.commit()

    @classmethod
    def get_for_team(cls, team_id, scraper_id=None):
        query = cls.query.filter_by(team_id=team_id)
        if scraper_id is not None:
            query = query.filter_by(scraper_id=scraper_id)
        return query.all()


def get_pending_player_departure_model():
    """Zwraca konkretną klasę BasePendingPlayerDepartureMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'pending_player_departures'
                and issubclass(cls, BasePendingPlayerDepartureMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BasePendingPlayerDepartureMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_pending_player_departure_model()."
    )
