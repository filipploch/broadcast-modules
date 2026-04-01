"""ShootoutKick model - individual kick record in a penalty shootout"""
from app.extensions import db
from datetime import datetime


class ShootoutKick(db.Model):
    """
    Pojedynczy rzut karny w konkursie rzutów karnych.

    Każdy wiersz = jeden rzut jednego zawodnika.

    Relacje
    -------
    shootout_id  → Shootout  (konkurs)
    game_id      → Game      (redundantny FK dla szybkich zapytań bez JOIN)
    player_id    → Player    (wykonujący zawodnik)

    Kolejność
    ---------
    round_number  : kolejka (1, 2, 3 … — minimum MIN_ROUNDS = 3)
    kick_order    : pozycja w kolejce (1 = home strzela, 2 = away strzela)

    Wynik
    -----
    scored : True = bramka, False = brak bramki, None = jeszcze niewykonany
    """

    __tablename__ = 'shootout_kicks'

    MIN_ROUNDS = 3

    TEAM_HOME = 'home'
    TEAM_AWAY = 'away'
    VALID_TEAMS = (TEAM_HOME, TEAM_AWAY)

    # ── Klucze ───────────────────────────────────────────────────────────────
    id          = db.Column(db.Integer, primary_key=True)
    shootout_id = db.Column(db.Integer, db.ForeignKey('shootouts.id'),
                            nullable=False, index=True)
    game_id     = db.Column(db.Integer, db.ForeignKey('games.id'),
                            nullable=False, index=True)
    player_id   = db.Column(db.Integer, db.ForeignKey('players.id'),
                            nullable=True, index=True)

    # ── Drużyna ──────────────────────────────────────────────────────────────
    team    = db.Column(db.String(10), nullable=False)   # 'home' | 'away'
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'),
                        nullable=True, index=True)

    # ── Kolejność ────────────────────────────────────────────────────────────
    round_number = db.Column(db.Integer, nullable=False)
    kick_order   = db.Column(db.Integer, nullable=False)

    # ── Wynik ────────────────────────────────────────────────────────────────
    # True = bramka, False = brak bramki, None = jeszcze niewykonany
    scored = db.Column(db.Boolean, nullable=True)

    # ── Znaczniki czasu ──────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    # ── Relacje ──────────────────────────────────────────────────────────────
    shootout = db.relationship(
        'Shootout',
        backref=db.backref(
            'kicks',
            lazy='dynamic',
            order_by='ShootoutKick.round_number, ShootoutKick.kick_order',
            cascade='all, delete-orphan'
        )
    )
    game = db.relationship(
        'Game',
        backref=db.backref('shootout_kicks', lazy='dynamic')
    )
    player = db.relationship(
        'Player',
        backref=db.backref('shootout_kicks', lazy='dynamic')
    )
    team_rel = db.relationship(
        'Team',
        backref=db.backref('shootout_kicks', lazy='dynamic')
    )

    # ── Indeksy i ograniczenia ───────────────────────────────────────────────
    __table_args__ = (
        # Jeden rzut per (konkurs, kolejka, pozycja)
        db.UniqueConstraint('shootout_id', 'round_number', 'kick_order',
                            name='uq_shootout_kick_position'),
        db.Index('ix_shootout_kick_game_round', 'game_id', 'round_number'),
    )

    # ── Reprezentacja ────────────────────────────────────────────────────────
    def __repr__(self):
        scored_str = {True: 'BRAMKA', False: 'BRAK', None: 'oczekuje'}.get(self.scored)
        return (
            f'<ShootoutKick konkurs={self.shootout_id} game={self.game_id} '
            f'kolejka={self.round_number} pozycja={self.kick_order} '
            f'drużyna={self.team} wynik={scored_str}>'
        )

    # ── Właściwości ───────────────────────────────────────────────────────────
    @property
    def is_pending(self):
        """Rzut jeszcze niewykonany."""
        return self.scored is None

    # ── Metody domenowe ───────────────────────────────────────────────────────
    def set_result(self, scored: bool):
        """
        Zapisz wynik rzutu.

        Args:
            scored: True = bramka, False = brak bramki
        """
        if not isinstance(scored, bool):
            raise ValueError("scored musi być True lub False")
        self.scored     = scored
        self.updated_at = datetime.utcnow()

    # ── Serializacja ─────────────────────────────────────────────────────────
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
