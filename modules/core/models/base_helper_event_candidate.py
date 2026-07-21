"""BaseHelperEventCandidateMixin — zdeduplikowana propozycja zdarzenia (albo
korekty istniejącego zdarzenia) zgłoszona przez jednego lub więcej
pomocników, oczekująca na decyzję operatora.

Odpowiednik PendingTeamMatch/PendingPlayerMatch dla scraperów: surowe
zgłoszenia (HelperEventSubmission) nigdy nie trafiają do GameEvent
bezpośrednio, tylko przez ten "kandydacki" wiersz, który operator
zatwierdza albo odrzuca. Patrz docs/helper-app-design.md.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseHelperEventCandidateMixin:

    KIND_NEW         = 'new'
    KIND_CORRECTION  = 'correction'

    STATUS_PENDING       = 'pending'
    STATUS_APPROVED      = 'approved'
    STATUS_REJECTED      = 'rejected'
    STATUS_AUTO_REJECTED = 'auto_rejected'

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)

    @declared_attr
    def period_id(cls):
        return db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=False, index=True)

    kind = db.Column(db.String(20), nullable=False, default=KIND_NEW)

    @declared_attr
    def event_id(cls):
        return db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)

    @declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    @declared_attr
    def player_id(cls):
        return db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)

    event_time_delta_s = db.Column(db.Integer, nullable=False)
    comment    = db.Column(db.String(500), nullable=True)

    @declared_attr
    def source_game_event_id(cls):
        # Wypełnione tylko dla kind=='correction' — wskazuje GameEvent do poprawy.
        return db.Column(db.Integer, db.ForeignKey('game_events.id'), nullable=True, index=True)

    status        = db.Column(db.String(20), nullable=False, default=STATUS_PENDING, index=True)
    status_reason = db.Column(db.String(300), nullable=True)

    @declared_attr
    def resolved_game_event_id(cls):
        return db.Column(db.Integer, db.ForeignKey('game_events.id'), nullable=True)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    @declared_attr
    def submissions(cls):
        return db.relationship(
            'HelperEventSubmission',
            backref='candidate',
            foreign_keys='HelperEventSubmission.candidate_id',
            order_by='HelperEventSubmission.submitted_at',
        )

    @declared_attr
    def game(cls):
        return db.relationship('Game', foreign_keys=[cls.game_id])

    @declared_attr
    def period(cls):
        return db.relationship('Period', foreign_keys=[cls.period_id])

    @declared_attr
    def event(cls):
        return db.relationship('Event', foreign_keys=[cls.event_id])

    @declared_attr
    def team(cls):
        return db.relationship('Team', foreign_keys=[cls.team_id])

    @declared_attr
    def player(cls):
        return db.relationship('Player', foreign_keys=[cls.player_id])

    def __repr__(self):
        return f'<HelperEventCandidate id={self.id} kind={self.kind} status={self.status}>'

    def to_dict(self):
        return {
            'id':                    self.id,
            'game_id':               self.game_id,
            'period_id':             self.period_id,
            'kind':                  self.kind,
            'event_id':              self.event_id,
            'team_id':               self.team_id,
            'player_id':             self.player_id,
            'event_time_delta_s':    self.event_time_delta_s,
            'comment':               self.comment,
            'source_game_event_id':  self.source_game_event_id,
            'event_name':            self.event.name if self.event else None,
            'team_name':             self.team.name if self.team else None,
            'player_name':           self.player.full_name if self.player else None,
            'status':                self.status,
            'status_reason':         self.status_reason,
            'resolved_game_event_id': self.resolved_game_event_id,
            'created_at':            self.created_at.isoformat() if self.created_at else None,
            'resolved_at':           self.resolved_at.isoformat() if self.resolved_at else None,
            'helper_names': [
                s.helper.display_name or s.helper.external_id
                for s in self.submissions if s.helper
            ],
            'submission_count': len(self.submissions),
        }

    @classmethod
    def find_matching_pending(cls, game_id, period_id, kind, event_time_delta_s=None,
                               event_id=None, team_id=None,
                               source_game_event_id=None, tolerance_s=8):
        """Szuka istniejącego kandydata PENDING pasującego wg reguł dedup
        z docs/helper-app-design.md (sekcja 4-5). Nie tworzy niczego."""
        query = cls.query.filter_by(
            game_id=game_id, period_id=period_id, kind=kind, status=cls.STATUS_PENDING,
        )
        if kind == cls.KIND_CORRECTION:
            return query.filter_by(source_game_event_id=source_game_event_id).first()

        query = query.filter_by(event_id=event_id, team_id=team_id)
        for candidate in query.all():
            if abs(candidate.event_time_delta_s - event_time_delta_s) <= tolerance_s:
                return candidate
        return None

    @classmethod
    def get_for_game(cls, game_id, status=None):
        query = cls.query.filter_by(game_id=game_id)
        if status is not None:
            query = query.filter_by(status=status)
        return query.order_by(cls.event_time_delta_s).all()

    @classmethod
    def get_pending_for_league(cls, league_id):
        """Kandydaci PENDING dla wszystkich meczów danej ligi — do widoku
        przeglądu operatora (analogicznie do get_games_with_discrepancy)."""
        from core.models.base_game import get_game_model
        Game = get_game_model()
        return (cls.query
                .join(Game, Game.id == cls.game_id)
                .filter(Game.league_id == league_id, cls.status == cls.STATUS_PENDING)
                .order_by(cls.game_id, cls.event_time_delta_s)
                .all())


def get_helper_event_candidate_model():
    """Zwraca konkretną klasę BaseHelperEventCandidateMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'helper_event_candidates'
                and issubclass(cls, BaseHelperEventCandidateMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseHelperEventCandidateMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_helper_event_candidate_model()."
    )
