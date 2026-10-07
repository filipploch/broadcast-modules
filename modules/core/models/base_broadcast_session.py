"""BaseBroadcastSessionMixin / BaseSessionGameMixin — sesja transmisji i mecz w sesji (etap E1).

Sesja transmisji = jeden stream (wieczór). Najwyżej jedna sesja otwarta naraz: kolumna open_slot ma wartość 1,
dopóki sesja jest otwarta, i NULL po zamknięciu; UNIQUE na tej kolumnie pilnuje ograniczenia w bazie.

Mecz w sesji = pozycja na uporządkowanej liście sesji. Najwyżej jeden mecz aktywny w sesji:
active_slot ma wartość 1 dla aktywnego i NULL dla pozostałych; UNIQUE(session_id, active_slot).

Logika (otwarcie, zmiana meczu, zamknięcie) jest w core/managers/session_manager.py; modele tylko przechowują stan.
"""
from datetime import datetime

from core.extensions import db


class BaseBroadcastSessionMixin:

    STATUS_PREPARATION = 'preparation'   # przygotowanie: wybrany mecz, stream jeszcze nie ruszył
    STATUS_ON_AIR = 'on_air'             # na antenie: OBS zgłosił stream albo nagrywanie (lub operator wcisnął przycisk)
    STATUS_FINISHED = 'finished'         # zakończona ręcznie przez operatora
    OPEN_STATUSES = (STATUS_PREPARATION, STATUS_ON_AIR)

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PREPARATION, index=True)
    open_slot = db.Column(db.Integer, nullable=True, unique=True)

    started_at = db.Column(db.DateTime, nullable=True)     # przejście w "na antenie"
    ended_at = db.Column(db.DateTime, nullable=True)

    # Dane streamu (uzupełniane przez moduł na podstawie zdarzeń OBS)
    obs_scene = db.Column(db.String(200), nullable=True)
    obs_recording = db.Column(db.Boolean, nullable=False, default=False)
    obs_streaming = db.Column(db.Boolean, nullable=False, default=False)
    # Stan do odtworzenia po awarii (JSON); wypełniany w E2
    recovery_state = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @db.declared_attr
    def session_games(cls):
        return db.relationship('SessionGame', backref='session', lazy='dynamic',
                               order_by='SessionGame.position', cascade='all, delete-orphan')

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def __repr__(self):
        return f'<BroadcastSession {self.id} {self.status}>'


class BaseSessionGameMixin:

    STATUS_QUEUED = 'queued'
    STATUS_ACTIVE = 'active'
    STATUS_FINISHED = 'finished'

    id = db.Column(db.Integer, primary_key=True)
    position = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_QUEUED, index=True)
    active_slot = db.Column(db.Integer, nullable=True)
    profile_key = db.Column(db.String(100), nullable=True)   # profil rozgrywek (E2)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)

    @db.declared_attr
    def session_id(cls):
        return db.Column(db.Integer, db.ForeignKey('broadcast_sessions.id'), nullable=False, index=True)

    @db.declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)

    @db.declared_attr
    def game(cls):
        return db.relationship('Game', lazy='select')

    @db.declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('session_id', 'game_id', name='uq_session_game'),
            db.UniqueConstraint('session_id', 'position', name='uq_session_position'),
            db.UniqueConstraint('session_id', 'active_slot', name='uq_session_active'),
        )

    def __repr__(self):
        return f'<SessionGame session={self.session_id} game={self.game_id} {self.status}>'


def _find_model(tablename, base):
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if getattr(cls, '__tablename__', None) == tablename and issubclass(cls, base):
            return cls
    raise RuntimeError(f"Nie znaleziono modelu '{tablename}' w rejestrze SQLAlchemy "
                       f"(zaimportuj modele modułu przed użyciem).")


def get_broadcast_session_model():
    return _find_model('broadcast_sessions', BaseBroadcastSessionMixin)


def get_session_game_model():
    return _find_model('session_games', BaseSessionGameMixin)
