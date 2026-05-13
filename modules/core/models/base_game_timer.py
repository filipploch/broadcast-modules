"""BaseGameTimerMixin — abstrakcyjna klasa bazowa dla timerów meczowych.

Zawiera wspólne pola i logikę dla wszystkich dyscyplin:
  - identyfikacja (game_id, period_id, timer_type, team, plugin_timer_id)
  - stan zegara (elapsed_time_ms, limit_ms, state)
  - metody sync_from_plugin, apply_adjustment

Pola specyficzne dla dyscypliny (np. start_offset_ms, adjustment_ms
dla timerów kar w futsalu) dodawane są w klasie GameTimer modułu.
"""
from core.extensions import db
from datetime import datetime


class BaseGameTimerMixin:

    # ── Stałe ────────────────────────────────────────────────────────────────
    TYPE_MAIN    = 'main'
    TYPE_PENALTY = 'penalty'

    TEAM_HOME = 'home'
    TEAM_AWAY = 'away'

    STATE_IDLE          = 'idle'
    STATE_RUNNING       = 'running'
    STATE_PAUSED        = 'paused'
    STATE_LIMIT_REACHED = 'limit_reached'
    STATE_REMOVED       = 'removed'

    VALID_TYPES  = (TYPE_MAIN, TYPE_PENALTY)
    VALID_TEAMS  = (TEAM_HOME, TEAM_AWAY)
    VALID_STATES = (STATE_IDLE, STATE_RUNNING, STATE_PAUSED,
                    STATE_LIMIT_REACHED, STATE_REMOVED)

    # ── Kolumny wspólne ───────────────────────────────────────────────────────
    id         = db.Column(db.Integer, primary_key=True)
    timer_type = db.Column(db.String(20), nullable=False)
    team       = db.Column(db.String(10), nullable=True)

    plugin_timer_id = db.Column(db.String(200), nullable=True, unique=True)

    elapsed_time_ms = db.Column(db.Integer, nullable=False, default=0)
    limit_ms        = db.Column(db.Integer, nullable=True)
    state           = db.Column(db.String(20), nullable=False,
                                default='idle', index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    # ── FK przez @db.declared_attr ────────────────────────────────────────────
    @db.declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'),
                         nullable=False, index=True)

    @db.declared_attr
    def period_id(cls):
        return db.Column(db.Integer, db.ForeignKey('periods.id'),
                         nullable=True, index=True)

    @db.declared_attr
    def player_id(cls):
        return db.Column(db.Integer, db.ForeignKey('players.id'),
                         nullable=True, index=True)

    # ── Relacje ───────────────────────────────────────────────────────────────



    @db.declared_attr
    def __table_args__(cls):
        return (
            db.Index('ix_game_timer_game_state',    'game_id', 'state'),
            db.Index('ix_game_timer_game_type_team', 'game_id', 'timer_type', 'team'),
        )

    # ── Właściwości ───────────────────────────────────────────────────────────
    @property
    def remaining_ms(self):
        if self.limit_ms is None:
            return None
        return max(0, self.limit_ms - self.elapsed_time_ms)

    @property
    def is_active(self):
        return self.state in (self.STATE_IDLE, self.STATE_RUNNING, self.STATE_PAUSED)

    # ── Metody domenowe ───────────────────────────────────────────────────────
    def sync_from_plugin(self, elapsed_time_ms: int, state: str):
        self.elapsed_time_ms = elapsed_time_ms
        self.state = state
        self.updated_at = datetime.utcnow()

    def apply_adjustment(self, delta_ms: int):
        """Ręczna korekta czasu. Moduł może rozszerzyć jeśli ma adjustment_ms."""
        self.updated_at = datetime.utcnow()

    def __repr__(self):
        return (f'<GameTimer id={self.id} type={self.timer_type} '
                f'game_id={self.game_id} state={self.state}>')

    def to_dict(self):
        return {
            'id':             self.id,
            'game_id':        self.game_id,
            'period_id':      self.period_id,
            'timer_type':     self.timer_type,
            'team':           self.team,
            'player_id':      self.player_id,
            'timer_id':       self.plugin_timer_id,
            'elapsed_time':   self.elapsed_time_ms,
            'initial_time':   self.period.initial_time if self.period else 0,
            'limit':          self.limit_ms,
            'remaining_ms':   self.remaining_ms,
            'state':          self.state,
            'created_at':     self.created_at.isoformat() if self.created_at else None,
            'updated_at':     self.updated_at.isoformat() if self.updated_at else None,
        }

def get_game_timer_model():
    """Zwraca klasę GameTimer zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_timers'
                and issubclass(cls, BaseGameTimerMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy GameTimer w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )