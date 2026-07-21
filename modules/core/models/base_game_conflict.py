"""BaseGameConflictMixin — niespójność danych meczu między dwoma scraperami
(np. superscore i malopolskizpn podają różny wynik albo różną datę), czekająca
na ręczną decyzję admina który scraper ma rację.

Wiersz NIE jest usuwany po rozwiązaniu (inaczej niż pozostałe kolejki Pending*
w tej aplikacji) — zostaje z wypełnionym resolved_at/resolved_scraper_id i
służy jako pamięć "ten dokładny konflikt już rozstrzygnięto", żeby kolejne
scrapowania (jeśli błąd na źródłowej stronie się nie poprawi) nie zgłaszały
go ponownie. Nowy, INNY konflikt dla tego samego meczu (inne wartości niż
ostatnio rozstrzygnięte) tworzy nowy otwarty wiersz.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseGameConflictMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)

    @declared_attr
    def league_id(cls):
        return db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False, index=True)

    @declared_attr
    def scraper_a_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False)

    scraper_a_home_goals    = db.Column(db.Integer, nullable=True)
    scraper_a_away_goals    = db.Column(db.Integer, nullable=True)
    scraper_a_home_ht_goals = db.Column(db.Integer, nullable=True)
    scraper_a_away_ht_goals = db.Column(db.Integer, nullable=True)
    scraper_a_date          = db.Column(db.DateTime, nullable=True)

    @declared_attr
    def scraper_b_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False)

    scraper_b_home_goals    = db.Column(db.Integer, nullable=True)
    scraper_b_away_goals    = db.Column(db.Integer, nullable=True)
    scraper_b_home_ht_goals = db.Column(db.Integer, nullable=True)
    scraper_b_away_ht_goals = db.Column(db.Integer, nullable=True)
    scraper_b_date          = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    @declared_attr
    def resolved_scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=True)

    @declared_attr
    def game(cls):
        return db.relationship('Game')

    @declared_attr
    def league(cls):
        return db.relationship('League')

    @declared_attr
    def scraper_a(cls):
        return db.relationship('Scraper', foreign_keys=[cls.scraper_a_id])

    @declared_attr
    def scraper_b(cls):
        return db.relationship('Scraper', foreign_keys=[cls.scraper_b_id])

    @declared_attr
    def resolved_scraper(cls):
        return db.relationship('Scraper', foreign_keys=[cls.resolved_scraper_id])

    def __repr__(self):
        return f'<GameConflict game_id={self.game_id} resolved={self.resolved_at is not None}>'

    def _fingerprint(self):
        """(scraper_id, home, away, date) dla obu stron, w kolejności rosnącej
        po scraper_id — porównywalne niezależnie od tego, który scraper aktualnie
        skanuje jako 'a' czy 'b'."""
        sides = sorted([
            (self.scraper_a_id, self.scraper_a_home_goals, self.scraper_a_away_goals, self.scraper_a_date),
            (self.scraper_b_id, self.scraper_b_home_goals, self.scraper_b_away_goals, self.scraper_b_date),
        ], key=lambda s: s[0])
        return tuple(sides)

    @classmethod
    def get_open_for_game(cls, game_id):
        return cls.query.filter_by(game_id=game_id, resolved_at=None).first()

    @classmethod
    def get_open_for_league(cls, league_id):
        return (cls.query
                .filter_by(league_id=league_id, resolved_at=None)
                .order_by(cls.created_at)
                .all())

    @classmethod
    def get_resolved_for_league(cls, league_id):
        """Konflikty już rozstrzygnięte przez admina dla tej ligi — do wglądu
        w historię (np. gdy ten sam, niepoprawiony błąd źródła jest po cichu
        pomijany przy kolejnych scrapowaniach zamiast zgłaszany ponownie)."""
        return (cls.query
                .filter(cls.league_id == league_id, cls.resolved_at.isnot(None))
                .order_by(cls.resolved_at.desc())
                .all())

    @classmethod
    def find_matching_resolution(cls, game_id, scraper_a_id, a_home, a_away, a_date,
                                  scraper_b_id, b_home, b_away, b_date):
        """Szuka już ROZWIĄZANEGO konfliktu dla tego meczu o identycznym
        fingerprintcie (te same wartości po obu stronach) — sygnał że to ten
        sam, niepoprawiony błąd źródła, a nie nowa niespójność."""
        candidate_fp = tuple(sorted([
            (scraper_a_id, a_home, a_away, a_date),
            (scraper_b_id, b_home, b_away, b_date),
        ], key=lambda s: s[0]))
        for row in cls.query.filter(cls.game_id == game_id, cls.resolved_at.isnot(None)).all():
            if row._fingerprint() == candidate_fp:
                return row
        return None

    @classmethod
    def upsert_open(cls, game_id, league_id, scraper_a_id, a_home, a_away, a_home_ht, a_away_ht, a_date,
                     scraper_b_id, b_home, b_away, b_home_ht, b_away_ht, b_date):
        """Utwórz albo odśwież otwarty (nierozwiązany) wiersz dla tego meczu."""
        row = cls.get_open_for_game(game_id)
        if row is None:
            row = cls(game_id=game_id, league_id=league_id)
            db.session.add(row)
        row.scraper_a_id           = scraper_a_id
        row.scraper_a_home_goals   = a_home
        row.scraper_a_away_goals   = a_away
        row.scraper_a_home_ht_goals = a_home_ht
        row.scraper_a_away_ht_goals = a_away_ht
        row.scraper_a_date         = a_date
        row.scraper_b_id           = scraper_b_id
        row.scraper_b_home_goals   = b_home
        row.scraper_b_away_goals   = b_away
        row.scraper_b_home_ht_goals = b_home_ht
        row.scraper_b_away_ht_goals = b_away_ht
        row.scraper_b_date         = b_date
        row.updated_at             = datetime.utcnow()
        db.session.commit()
        return row


def get_game_conflict_model():
    """Zwraca konkretną klasę BaseGameConflictMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_conflicts'
                and issubclass(cls, BaseGameConflictMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseGameConflictMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_game_conflict_model()."
    )
