"""BaseGameScraperSnapshotMixin — co konkretny scraper ostatnio zobaczył dla
danego meczu (wynik, wynik do przerwy, data).

Game przechowuje jeden, współdzielony stan (może być nadpisywany przez różne
scrapery tego samego meczu — patrz dedup w game_scraper_manager). Snapshot
per scraper jest potrzebny osobno, żeby przy kolejnym scrapowaniu dało się
porównać "co nowego mówi scraper X" z "co ostatnio mówił scraper Y", zamiast
tylko z aktualnym (już ewentualnie zmergowanym) stanem Game.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseGameScraperSnapshotMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def scraper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('scrapers.id'), nullable=False, index=True)

    @declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)

    home_team_goals = db.Column(db.Integer, nullable=True)
    away_team_goals = db.Column(db.Integer, nullable=True)
    home_ht_goals   = db.Column(db.Integer, nullable=True)
    away_ht_goals   = db.Column(db.Integer, nullable=True)
    date            = db.Column(db.DateTime, nullable=True)
    status          = db.Column(db.Integer, nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def scraper(cls):
        return db.relationship('Scraper')

    @declared_attr
    def game(cls):
        return db.relationship('Game')

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('scraper_id', 'game_id', name='uix_game_scraper_snapshot_scraper_game'),
        )

    def __repr__(self):
        return (f'<GameScraperSnapshot scraper_id={self.scraper_id} game_id={self.game_id} '
                f'{self.home_team_goals}:{self.away_team_goals}>')

    @classmethod
    def get(cls, scraper_id, game_id):
        return cls.query.filter_by(scraper_id=scraper_id, game_id=game_id).first()

    @classmethod
    def get_other(cls, game_id, exclude_scraper_id):
        """Zwraca snapshot INNEGO scrapera dla tego meczu (jeśli jakikolwiek istnieje)."""
        return (cls.query
                .filter(cls.game_id == game_id, cls.scraper_id != exclude_scraper_id)
                .first())

    @classmethod
    def get_all_for_game(cls, game_id):
        """Zwraca snapshoty WSZYSTKICH scraperów dla tego meczu — do porównania
        N źródeł naraz (nie tylko pary), patrz raport niespójności."""
        return cls.query.filter_by(game_id=game_id).all()

    @classmethod
    def get_games_with_discrepancy(cls, league_id):
        """
        Mecze tej ligi, dla których snapshoty różnych scraperów (plus wynik
        oficjalny, jeśli mecz ma is_edited — atrybut specyficzny dla modułów,
        które go obsługują, stąd getattr) nie zgadzają się co do wyniku
        pełnego czasu gry i/lub daty (wynik do przerwy nigdy nie jest polem
        konfliktowym). Współdzielone: core używa tego do samego licznika
        (badge na liście meczów), moduł (np. garbarnia) buduje na tej
        podstawie pełny raport ze szczegółami źródeł.
        """
        from core.models.base_game import get_game_model
        Game = get_game_model()

        games = Game.query.filter_by(league_id=league_id).all()
        result = []
        for game in games:
            snaps = cls.query.filter_by(game_id=game.id).all()
            if not snaps:
                continue
            values = [(s.home_team_goals, s.away_team_goals, s.date) for s in snaps]
            if getattr(game, 'is_edited', False):
                values.append((game.home_team_goals, game.away_team_goals, game.date))
            if cls._values_disagree(values):
                result.append(game)
        return result

    @staticmethod
    def _values_disagree(values):
        """`values` to lista (home_goals, away_goals, date) — True jeśli
        którekolwiek dwie mają różne (oba niepuste) wartości w którymkolwiek
        z tych trzech pól."""
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                for a, b in zip(values[i], values[j]):
                    if a is not None and b is not None and a != b:
                        return True
        return False

    @classmethod
    def upsert(cls, scraper_id, game_id, home_team_goals, away_team_goals,
               home_ht_goals, away_ht_goals, date, status):
        row = cls.get(scraper_id, game_id)
        if row:
            row.home_team_goals = home_team_goals
            row.away_team_goals = away_team_goals
            row.home_ht_goals   = home_ht_goals
            row.away_ht_goals   = away_ht_goals
            row.date            = date
            row.status          = status
            row.updated_at      = datetime.utcnow()
        else:
            row = cls(
                scraper_id=scraper_id, game_id=game_id,
                home_team_goals=home_team_goals, away_team_goals=away_team_goals,
                home_ht_goals=home_ht_goals, away_ht_goals=away_ht_goals,
                date=date, status=status,
            )
            db.session.add(row)
        db.session.commit()
        return row


def get_game_scraper_snapshot_model():
    """Zwraca konkretną klasę BaseGameScraperSnapshotMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_scraper_snapshots'
                and issubclass(cls, BaseGameScraperSnapshotMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseGameScraperSnapshotMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_game_scraper_snapshot_model()."
    )
