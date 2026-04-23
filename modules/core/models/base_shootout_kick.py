"""BaseShootoutKickMixin — abstrakcyjna klasa bazowa dla rzutów karnych w konkursie."""
from core.extensions import db
from datetime import datetime


class BaseShootoutKickMixin:
    """
    Pojedynczy rzut karny w konkursie rzutów karnych.

    Stałe które moduł może nadpisać:
        MIN_ROUNDS — minimalna liczba kolejek (futsal=3, piłka nożna=5)

    Relacje:
        Backrefy definiowane po stronie "parent":
          - 'kicks'          → przez Shootout.kicks
          - 'shootout_kicks' → przez Game i Player i Team
        BaseShootoutKickMixin definiuje tylko swoją stronę relacji (bez backref).
    """

    # Stała do nadpisania w module — domyślna wartość dla większości dyscyplin
    MIN_ROUNDS = 5  # piłka nożna: 5 kolejek; futsal nadpisze na 3

    TEAM_HOME   = 'home'
    TEAM_AWAY   = 'away'
    VALID_TEAMS = (TEAM_HOME, TEAM_AWAY)

    # ── Kolumny zwykłe ────────────────────────────────────────────────────────
    id           = db.Column(db.Integer, primary_key=True)
    team         = db.Column(db.String(10), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    kick_order   = db.Column(db.Integer, nullable=False)
    scored       = db.Column(db.Boolean, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    # ── FK przez @db.declared_attr ────────────────────────────────────────────
    @db.declared_attr
    def shootout_id(cls):
        return db.Column(db.Integer, db.ForeignKey('shootouts.id'),
                         nullable=False, index=True)

    @db.declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'),
                         nullable=False, index=True)

    @db.declared_attr
    def player_id(cls):
        return db.Column(db.Integer, db.ForeignKey('players.id'),
                         nullable=True, index=True)

    @db.declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'),
                         nullable=True, index=True)

    # ── Relacje bez backref ───────────────────────────────────────────────────
    # Backrefy ('kicks', 'shootout_kicks') definiowane są po stronie Shootout,
    # Game, Player, Team — nie tutaj. Zasada: jedna strona definiuje backref.
    @db.declared_attr
    def shootout(cls):
        return db.relationship('Shootout', lazy='select')

    @db.declared_attr
    def game(cls):
        return db.relationship('Game', lazy='select')

    @db.declared_attr
    def player(cls):
        return db.relationship('Player', lazy='select')

    @db.declared_attr
    def team_rel(cls):
        return db.relationship('Team', lazy='select')

    # ── Indeksy i ograniczenia ────────────────────────────────────────────────
    @db.declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('shootout_id', 'round_number', 'kick_order',
                                name='uq_shootout_kick_position'),
            db.Index('ix_shootout_kick_game_round', 'game_id', 'round_number'),
        )

    # ── Właściwości ───────────────────────────────────────────────────────────
    @property
    def is_pending(self):
        return self.scored is None

    # ── Metody domenowe ───────────────────────────────────────────────────────
    def set_result(self, scored: bool):
        if not isinstance(scored, bool):
            raise ValueError("scored musi być True lub False")
        self.scored     = scored
        self.updated_at = datetime.utcnow()

    def __repr__(self):
        scored_str = {True: 'BRAMKA', False: 'BRAK', None: 'oczekuje'}.get(self.scored)
        return (f'<ShootoutKick konkurs={self.shootout_id} game={self.game_id} '
                f'kolejka={self.round_number} pozycja={self.kick_order} '
                f'drużyna={self.team} wynik={scored_str}>')

    def to_dict(self):
        return {
            'id':           self.id,
            'shootout_id':  self.shootout_id,
            'game_id':      self.game_id,
            'player_id':    self.player_id,
            'team':         self.team,
            'team_id':      self.team_id,
            'round_number': self.round_number,
            'kick_order':   self.kick_order,
            'scored':       self.scored,
            'is_pending':   self.is_pending,
            'created_at':   self.created_at.isoformat() if self.created_at else None,
            'updated_at':   self.updated_at.isoformat() if self.updated_at else None,
        }

def get_shootout_kick_model():
    """Zwraca konkretną klasę ShootoutKick zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'shootout_kicks'
                and issubclass(cls, BaseShootoutKickMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy ShootoutKick w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_shootout_kick_model()."
    )