"""BaseShootoutMixin — abstrakcyjna klasa bazowa dla konkursów rzutów karnych."""
from core.extensions import db
from datetime import datetime


class BaseShootoutMixin:

    id = db.Column(db.Integer, primary_key=True)

    # Wynik konkursu
    home_team_shootouts = db.Column(db.Integer, default=0, nullable=False)
    away_team_shootouts = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    # FK przez @db.declared_attr — wymagane w klasach abstrakcyjnych
    @db.declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'),
                         nullable=False, unique=True, index=True)

    # Relacja — backref 'shootout' definiowany w BaseGameMixin.shootout (po stronie Game)
    # @db.declared_attr
    # def game(cls):
    #     return db.relationship('Game', lazy='select')

    def __repr__(self):
        return (f'<Shootout game_id={self.game_id}: '
                f'{self.home_team_shootouts}:{self.away_team_shootouts}>')

    @property
    def winner_id(self):
        if self.home_team_shootouts > self.away_team_shootouts:
            return self.game.home_team_id if self.game else None
        elif self.away_team_shootouts > self.home_team_shootouts:
            return self.game.away_team_id if self.game else None
        return None

    @property
    def score_string(self):
        return f"{self.home_team_shootouts}:{self.away_team_shootouts}"

    def update_score(self, home, away):
        self.home_team_shootouts = home
        self.away_team_shootouts = away
        self.updated_at = datetime.utcnow()

    def increment_home_shootouts(self):
        self.home_team_shootouts += 1
        self.updated_at = datetime.utcnow()

    def increment_away_shootouts(self):
        self.away_team_shootouts += 1
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        return {
            'id':                   self.id,
            'game_id':              self.game_id,
            'home_team_shootouts':  self.home_team_shootouts,
            'away_team_shootouts':  self.away_team_shootouts,
            'score_string':         self.score_string,
            'winner_id':            self.winner_id,
            'created_at':           self.created_at.isoformat() if self.created_at else None,
            'updated_at':           self.updated_at.isoformat() if self.updated_at else None,
        }

def get_shootout_model():
    """Zwraca konkretną klasę Shootout zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'shootouts'
                and issubclass(cls, BaseShootoutMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Shootout w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_shootout_model()."
    )