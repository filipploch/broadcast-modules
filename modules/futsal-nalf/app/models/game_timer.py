"""GameTimer model - persistent state of timers tied to a game"""
from app.extensions import db
from datetime import datetime


class GameTimer(db.Model):
    """
    Persistent state of a single timer tied to a specific game and period.

    Replaces the ad-hoc JSON blob stored in settings.current_timers.

    Timer types
    -----------
    'main'
        One per period — the running match clock managed by timer-plugin.
        plugin_timer_id points to the actual timer instance in the plugin.

    'penalty'
        Zero or more per period, one per foul served.
        In the current (legacy) architecture: plugin_timer_id points to a
        dependent timer in timer-plugin.
        In the upcoming derived-variable architecture: plugin_timer_id is NULL
        and the remaining time is calculated from the main timer's elapsed_time
        using start_offset_ms + adjustment_ms.

    Lifecycle states (state column)
    --------------------------------
    idle            Created but not yet started
    running         Actively counting
    paused          Temporarily stopped (e.g. main timer paused mid-period)
    limit_reached   Timer reached its limit (penalty served / period over)
    removed         Manually cancelled before limit (soft-delete)
    """

    __tablename__ = 'game_timers'

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

    # ── Klucze główne i obce ─────────────────────────────────────────────────
    id        = db.Column(db.Integer, primary_key=True)
    game_id   = db.Column(db.Integer, db.ForeignKey('games.id'),
                          nullable=False, index=True)
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id'),
                          nullable=True, index=True)

    # ── Klasyfikacja ─────────────────────────────────────────────────────────
    timer_type = db.Column(db.String(20), nullable=False)
    # NULL dla main / zdarzeń bez drużyny
    team       = db.Column(db.String(10), nullable=True)
    # NULL gdy kara nie jest przypisana konkretnemu zawodnikowi
    player_id  = db.Column(db.Integer, db.ForeignKey('players.id'),
                           nullable=True, index=True)

    # ── Identyfikator w timer-plugin ─────────────────────────────────────────
    # NULL w nowej architekturze (derived-variable) dla timerów penalty
    plugin_timer_id = db.Column(db.String(200), nullable=True, unique=True)

    # ── Stan zegara (synchronizowany z pluginem przy każdym ticku) ───────────
    elapsed_time_ms = db.Column(db.Integer, nullable=False, default=0)
    limit_ms        = db.Column(db.Integer, nullable=True)
    state           = db.Column(db.String(20), nullable=False,
                                default=STATE_IDLE, index=True)

    # ── Pola dla nowej architektury (derived-variable penalty) ───────────────
    # elapsed_time_ms głównego timera w chwili nałożenia kary
    start_offset_ms = db.Column(db.Integer, nullable=True)
    # Suma ręcznych korekt (+/-) w ms
    adjustment_ms   = db.Column(db.Integer, nullable=False, default=0)

    # ── Znaczniki czasu ──────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    # ── Relacje ──────────────────────────────────────────────────────────────
    game   = db.relationship('Game',   backref=db.backref('game_timers',
                             lazy='dynamic', cascade='all, delete-orphan'))
    period = db.relationship('Period', backref=db.backref('game_timers',
                             lazy='dynamic'))
    player = db.relationship('Player', backref=db.backref('penalty_timers',
                             lazy='dynamic'))

    # ── Indeksy złożone ──────────────────────────────────────────────────────
    __table_args__ = (
        # Szybkie pobieranie aktywnych timerów danego meczu
        db.Index('ix_game_timer_game_state',  'game_id',   'state'),
        # Szybkie pobieranie aktywnych kar per drużyna
        db.Index('ix_game_timer_game_type_team', 'game_id', 'timer_type', 'team'),
    )

    # ── Reprezentacja ────────────────────────────────────────────────────────
    def __repr__(self):
        return (
            f'<GameTimer id={self.id} type={self.timer_type} '
            f'game_id={self.game_id} state={self.state}>'
        )

    # ── Właściwości obliczane ─────────────────────────────────────────────────

    @property
    def remaining_ms(self):
        """
        Pozostały czas w ms.

        Dla timerów z limitem: limit - elapsed.
        Dla timerów bez limitu (stoper): zwraca None.
        """
        if self.limit_ms is None:
            return None
        return max(0, self.limit_ms - self.elapsed_time_ms)

    def penalty_remaining_ms(self, main_elapsed_ms: int) -> int:
        """
        Pozostały czas kary obliczony na podstawie elapsed_time głównego
        timera (architektura derived-variable).

        Używać tylko dla timer_type == 'penalty' z wypełnionym start_offset_ms.

        Args:
            main_elapsed_ms: Aktualny elapsed_time głównego timera (ms)

        Returns:
            Pozostały czas kary w ms (min. 0)
        """
        if self.start_offset_ms is None or self.limit_ms is None:
            raise ValueError(
                f'GameTimer id={self.id}: start_offset_ms lub limit_ms nie są ustawione'
            )
        elapsed_in_penalty = (
            main_elapsed_ms - self.start_offset_ms + self.adjustment_ms
        )
        return max(0, self.limit_ms - elapsed_in_penalty)

    @property
    def is_active(self):
        """True jeśli kara/timer jest aktywna (nie zakończona, nie usunięta)."""
        return self.state in (self.STATE_IDLE, self.STATE_RUNNING, self.STATE_PAUSED)

    # ── Metody domenowe ───────────────────────────────────────────────────────

    def sync_from_plugin(self, elapsed_time_ms: int, state: str):
        """
        Aktualizuje stan timera danymi z timer-plugin.
        Nie commituje — wywołujący zarządza transakcją.
        """
        self.elapsed_time_ms = elapsed_time_ms
        self.state = state
        self.updated_at = datetime.utcnow()

    def apply_adjustment(self, delta_ms: int):
        """
        Dodaje ręczną korektę czasu (może być ujemna).
        Nie commituje — wywołujący zarządza transakcją.
        """
        self.adjustment_ms += delta_ms
        self.updated_at = datetime.utcnow()

    # ── Serializacja ─────────────────────────────────────────────────────────

    def to_dict(self):
        return {
            'id':               self.id,
            'game_id':          self.game_id,
            'period_id':        self.period_id,
            'timer_type':       self.timer_type,
            'team':             self.team,
            'player_id':        self.player_id,
            'timer_id':         self.plugin_timer_id,
            'elapsed_time':     self.elapsed_time_ms,
            'initial_time':     self.period.initial_time,
            'limit':            self.limit_ms,
            'remaining_ms':     self.remaining_ms,
            'state':            self.state,
            'start_offset_ms':  self.start_offset_ms,
            'adjustment_ms':    self.adjustment_ms,
            'created_at':       self.created_at.isoformat() if self.created_at else None,
            'updated_at':       self.updated_at.isoformat() if self.updated_at else None,
        }
