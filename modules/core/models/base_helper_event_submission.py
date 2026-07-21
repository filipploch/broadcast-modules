"""BaseHelperEventSubmissionMixin — surowy log pojedynczych zgłoszeń od
pomocników. Nigdy nie modyfikowany po zapisie (ta sama zasada co
GameScraperSnapshot: surowe dane osobno od zmergowanego "kandydata").
Patrz docs/helper-app-design.md.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseHelperEventSubmissionMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def helper_id(cls):
        return db.Column(db.Integer, db.ForeignKey('helpers.id'), nullable=False, index=True)

    @declared_attr
    def candidate_id(cls):
        return db.Column(db.Integer, db.ForeignKey('helper_event_candidates.id'), nullable=False, index=True)

    @declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)

    @declared_attr
    def period_id(cls):
        return db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=False, index=True)

    elapsed_ms = db.Column(db.Integer, nullable=False)

    @declared_attr
    def event_id(cls):
        return db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)

    @declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    @declared_attr
    def player_id(cls):
        return db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)

    comment = db.Column(db.String(500), nullable=True)

    @declared_attr
    def source_game_event_id(cls):
        return db.Column(db.Integer, db.ForeignKey('game_events.id'), nullable=True)

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    @declared_attr
    def helper(cls):
        return db.relationship('Helper')

    def __repr__(self):
        return f'<HelperEventSubmission id={self.id} helper_id={self.helper_id} candidate_id={self.candidate_id}>'

    def to_dict(self):
        return {
            'id':                   self.id,
            'helper_id':            self.helper_id,
            'helper_name':          (self.helper.display_name or self.helper.external_id) if self.helper else None,
            'candidate_id':         self.candidate_id,
            'game_id':              self.game_id,
            'period_id':            self.period_id,
            'elapsed_ms':           self.elapsed_ms,
            'event_id':             self.event_id,
            'team_id':              self.team_id,
            'player_id':            self.player_id,
            'comment':              self.comment,
            'source_game_event_id': self.source_game_event_id,
            'submitted_at':         self.submitted_at.isoformat() if self.submitted_at else None,
        }


def get_helper_event_submission_model():
    """Zwraca konkretną klasę BaseHelperEventSubmissionMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'helper_event_submissions'
                and issubclass(cls, BaseHelperEventSubmissionMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseHelperEventSubmissionMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_helper_event_submission_model()."
    )
