"""BasePlayerMixin — abstrakcyjna klasa bazowa dla modeli zawodnika we wszystkich modułach.

Zawiera pola wspólne dla wszystkich dyscyplin.
Pola specyficzne dla dyscypliny (np. is_goalkeeper, is_captain w futsalu,
is_youth w piłce nożnej) dodawane są w klasie Player konkretnego modułu.
"""
from core.extensions import db
from datetime import datetime


class BasePlayerMixin:

    id         = db.Column(db.Integer, primary_key=True)
    foreign_id = db.Column(db.String(500), nullable=True)

    first_name = db.Column(db.String(100), nullable=False)
    last_name  = db.Column(db.String(100), nullable=False)
    number     = db.Column(db.Integer, nullable=True)

    @db.declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'),
                         nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    @db.declared_attr
    def game_players(cls):
        return db.relationship('GamePlayer', backref='player',
                               lazy='dynamic', cascade='all, delete-orphan')

    @db.declared_attr
    def game_events(cls):
        return db.relationship('GameEvent', backref='player', lazy='dynamic')

    @db.declared_attr
    def penalty_timers(cls):
        return db.relationship('GameTimer', backref='player', lazy='dynamic')

    def __repr__(self):
        return f'<Player {self.first_name} {self.last_name} (Team: {self.team_id})>'

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def short_name(self):
        return f"{self.first_name[0]}. {self.last_name}" if self.first_name else self.last_name

    @property
    def display_name(self):
        """Bazowa wersja — moduł może nadpisać żeby dodać wskaźniki (C), (GK) itd."""
        return self.full_name

    def to_dict(self):
        return {
            'id':         self.id,
            'foreign_id': self.foreign_id,
            'first_name': self.first_name,
            'last_name':  self.last_name,
            'number':     self.number,
            'full_name':  self.full_name,
            'short_name': self.short_name,
            'display_name': self.display_name,
            'team_id':    self.team_id,
            'team_name':  self.team.name if self.team else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


def get_player_model():
    """Zwraca klasę Player zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'players'
                and issubclass(cls, BasePlayerMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Player w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
