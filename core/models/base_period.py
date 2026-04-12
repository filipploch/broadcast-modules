"""BasePeriod — abstrakcyjna klasa bazowa dla modeli okresu gry.

Zawiera wspólne pola i logikę dla wszystkich dyscyplin:
  - konfiguracja timera (initial_time, limit, pause_at_limit)
  - wynik okresu (home/away_team_goals)
  - status i kolejność

Pola specyficzne dla dyscypliny (np. faule w futsalu) dodawane
są w klasie Period konkretnego modułu.
"""
from core.extensions import db
from datetime import datetime


class BasePeriod(db.Model):
    __abstract__ = True

    STATUS_NOT_STARTED = 0
    STATUS_PENDING     = 1
    STATUS_FINISHED    = 2

    id           = db.Column(db.Integer, primary_key=True)
    period_order = db.Column(db.Integer, nullable=False)
    description  = db.Column(db.String(100), nullable=False)
    main_timer_name = db.Column(db.String(200), nullable=True)

    # Wynik okresu
    home_team_goals = db.Column(db.Integer, default=0, nullable=False)
    away_team_goals = db.Column(db.Integer, default=0, nullable=False)

    # Ustawienia timera (ms)
    initial_time   = db.Column(db.Integer, default=0,       nullable=False)
    limit          = db.Column(db.Integer, default=1200000, nullable=False)
    pause_at_limit = db.Column(db.Boolean, default=True,    nullable=False)

    status     = db.Column(db.Integer, default=0, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @db.declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'),
                         nullable=False, index=True)

    @db.declared_attr
    def game_events(cls):
        return db.relationship('GameEvent', backref='period',
                               lazy='dynamic', cascade='all, delete-orphan')

    @db.declared_attr
    def game_timers(cls):
        return db.relationship('GameTimer', backref='period', lazy='dynamic')

    @db.declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('game_id', 'period_order',
                                name='unique_game_period_order'),
        )

    def __repr__(self):
        return f'<Period {self.period_order} game_id={self.game_id}: {self.description}>'

    def get_status_text(self):
        return {
            self.STATUS_NOT_STARTED: 'Nie rozpoczęto',
            self.STATUS_PENDING:     'Trwa',
            self.STATUS_FINISHED:    'Zakończono',
        }.get(self.status, 'Nieznany')

    def generate_timer_name(self):
        if not self.game:
            return None
        home = self.game.home_team.short_name if self.game.home_team else '???'
        away = self.game.away_team.short_name if self.game.away_team else '???'
        return f'{home}x{away} p:{self.period_order}'

    def update_timer_name(self):
        self.main_timer_name = self.generate_timer_name()
        self.updated_at = datetime.utcnow()

    @property
    def limit_seconds(self):
        return self.limit / 1000 if self.limit else 0

    @property
    def initial_time_seconds(self):
        return self.initial_time / 1000 if self.initial_time else 0

    def update_score(self, home_goals, away_goals):
        self.home_team_goals = home_goals
        self.away_team_goals = away_goals
        self.updated_at = datetime.utcnow()

    def increment_home_goals(self, value: int):
        if self.home_team_goals + value >= 0:
            self.home_team_goals += value
            self.updated_at = datetime.utcnow()

    def increment_away_goals(self, value: int):
        if self.away_team_goals + value >= 0:
            self.away_team_goals += value
            self.updated_at = datetime.utcnow()

    def sync_to_game(self):
        """Zsynchronizuj wynik okresu z rekordem meczu."""
        from core.extensions import db as _db
        game = self.game
        if not game:
            return
        all_periods = self.__class__.query.filter_by(game_id=self.game_id).all()
        game.home_team_goals = sum(p.home_team_goals for p in all_periods)
        game.away_team_goals = sum(p.away_team_goals for p in all_periods)
        game.updated_at = datetime.utcnow()
        _db.session.commit()

    @staticmethod
    def calculate_initial_time_for_period(period_cls, game_id, period_order):
        if period_order == 1:
            return 0
        previous = period_cls.query.filter(
            period_cls.game_id == game_id,
            period_cls.period_order < period_order
        ).all()
        return sum(p.limit for p in previous)

    def to_dict(self):
        return {
            'id':               self.id,
            'game_id':          self.game_id,
            'period_order':     self.period_order,
            'description':      self.description,
            'main_timer_name':  self.main_timer_name,
            'home_team_goals':  self.home_team_goals,
            'away_team_goals':  self.away_team_goals,
            'initial_time':     self.initial_time,
            'initial_time_seconds': self.initial_time_seconds,
            'limit':            self.limit,
            'limit_seconds':    self.limit_seconds,
            'pause_at_limit':   self.pause_at_limit,
            'status':           self.status,
            'status_text':      self.get_status_text(),
            'created_at':       self.created_at.isoformat() if self.created_at else None,
            'updated_at':       self.updated_at.isoformat() if self.updated_at else None,
        }
