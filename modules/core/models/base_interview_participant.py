"""BaseInterviewParticipantMixin — jeden wiersz listy "wywiadu" w zakładce
admina (patrz InterviewManager). Przechowuje ROZWIĄZANE, gotowe do wysłania
na overlay wartości (description/image_path), a nie tylko surowy wybór
użytkownika — dzięki temu "W" (toggle) nie musi nic przeliczać na nowo,
tylko wysłać to co jest zapisane.

Lista jest per-mecz (game_id) — RESET czyści tylko bieżący mecz, tak jak
inne dane "live" w tym repo (segmenty nagrań, eventy).
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseInterviewParticipantMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)

    # 'redaktor' | 'zawodnik' | 'sedzia' | 'trener' | 'inne'
    interview_type = db.Column(db.String(20), nullable=False)

    # Zawsze wolny tekst — nawet gdy dopasowany do osoby z bazy (patrz
    # InterviewManager.add: użytkownik może wpisać imię i nazwisko samemu
    # i zignorować podpowiedzi).
    name = db.Column(db.String(200), nullable=False)

    @declared_attr
    def matched_player_id(cls):
        return db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)

    @declared_attr
    def matched_referee_id(cls):
        return db.Column(db.Integer, db.ForeignKey('referees.id'), nullable=True)

    # 'redaktor' jest reprezentowany w bazie przez Commentator (tabela
    # commentators — ci sami komentatorzy co przy ustawieniach meczu).
    @declared_attr
    def matched_commentator_id(cls):
        return db.Column(db.Integer, db.ForeignKey('commentators.id'), nullable=True)

    @declared_attr
    def matched_team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    use_team_crest = db.Column(db.Boolean, default=False, nullable=False)

    # Rozwiązane finalne wartości wysyłane do overlay (update_interview) —
    # domyślny tekst/obrazek typu, albo nazwa/herb drużyny, albo wolny tekst.
    description = db.Column(db.String(300), nullable=True, default='')
    image_path = db.Column(db.String(500), nullable=True)

    # Co najwyżej jeden True per game_id — patrz InterviewManager.toggle().
    is_active = db.Column(db.Boolean, default=False, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @declared_attr
    def game(cls):
        return db.relationship('Game')

    @declared_attr
    def matched_player(cls):
        return db.relationship('Player')

    @declared_attr
    def matched_referee(cls):
        return db.relationship('Referee')

    @declared_attr
    def matched_commentator(cls):
        return db.relationship('Commentator')

    @declared_attr
    def matched_team(cls):
        return db.relationship('Team')

    def __repr__(self):
        return f'<InterviewParticipant {self.interview_type} {self.name} active={self.is_active}>'

    def to_dict(self):
        team_short_name = self.matched_team.short_name if self.matched_team else None
        return {
            'id': self.id,
            'game_id': self.game_id,
            'interview_type': self.interview_type,
            'name': self.name,
            'matched_player_id': self.matched_player_id,
            'matched_referee_id': self.matched_referee_id,
            'matched_commentator_id': self.matched_commentator_id,
            'matched_team_id': self.matched_team_id,
            'team_short_name': team_short_name,
            'use_team_crest': self.use_team_crest,
            'description': self.description,
            'image_path': self.image_path,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


def get_interview_participant_model():
    """Zwraca konkretną klasę BaseInterviewParticipantMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'interview_participants'
                and issubclass(cls, BaseInterviewParticipantMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseInterviewParticipantMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_interview_participant_model()."
    )
