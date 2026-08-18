from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    """Jeden model dla obu ról — admin i pomocnik — rozróżnianych polem `role`.

    Login pomocnika (`username`) odpowiada `external_id` wysyłanemu w
    zgłoszeniach do modułu głównego przez HelperRelay (patrz
    docs/helper-app-design.md w repo modułu głównego, sekcja 3).
    """

    __tablename__ = 'users'

    ROLE_ADMIN = 'admin'
    ROLE_HELPER = 'helper'
    ROLES = (ROLE_ADMIN, ROLE_HELPER)

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(128), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default=ROLE_HELPER)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self) -> bool:
        return self.role == self.ROLE_ADMIN

    @property
    def is_active(self) -> bool:
        # UserMixin domyślnie zwraca zawsze True — nadpisujemy własnym polem,
        # żeby admin mógł wyłączyć konto pomocnika bez usuwania go.
        return self.active

    def __repr__(self) -> str:
        return f'<User {self.username} ({self.role})>'


class SquadPush(db.Model):
    """Jedna 'paczka' kadry wysłana przez moduł główny dla (game_id, team_id).

    Pomocnik pracuje na tym rekordzie: przypisuje role graczom
    (`SquadPushPlayer.role`) i ewentualnie edytuje `coach_name`, po czym
    ustawia `status='submitted'` — to jedyny sygnał modułu głównego, że jest
    coś do pobrania (moduł główny woła GET /api/relay/squad/proposals,
    Render nigdy nie łączy się z modułem głównym — ten jest za NAT-em).
    """

    __tablename__ = 'squad_pushes'

    STATUS_OPEN      = 'open'
    STATUS_SUBMITTED = 'submitted'

    COACH_SOURCE_PUSHED = 'pushed'
    COACH_SOURCE_EDITED = 'edited'

    id = db.Column(db.Integer, primary_key=True)
    game_id    = db.Column(db.Integer, nullable=False, index=True)
    team_id    = db.Column(db.Integer, nullable=False, index=True)
    team_label = db.Column(db.String(200), nullable=True)

    coach_name        = db.Column(db.String(100), nullable=True)
    # 'edited' blokuje nadpisanie coach_name przy ponownym pushu z modułu
    # głównego — bez tego nie dałoby się odróżnić "operator wysłał to samo
    # nazwisko" od "pomocnik nic nie zmienił".
    coach_name_source = db.Column(db.String(10), nullable=False, default=COACH_SOURCE_PUSHED)

    status = db.Column(db.String(10), nullable=False, default=STATUS_OPEN)
    submitted_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    received_at  = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime, nullable=True)
    # Napędza okno retry przy GET /api/relay/squad/proposals — patrz relay.py.
    fetched_at   = db.Column(db.DateTime, nullable=True)

    players = db.relationship(
        'SquadPushPlayer', backref='squad_push',
        cascade='all, delete-orphan', order_by='SquadPushPlayer.last_name',
    )
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_user_id])

    def __repr__(self) -> str:
        return f'<SquadPush id={self.id} game_id={self.game_id} team_id={self.team_id} status={self.status}>'


class SquadPushPlayer(db.Model):
    __tablename__ = 'squad_push_players'

    ROLE_STARTER    = 'starter'
    ROLE_SUBSTITUTE = 'substitute'
    ROLE_NONE       = 'none'
    ROLES = (ROLE_STARTER, ROLE_SUBSTITUTE, ROLE_NONE)

    id = db.Column(db.Integer, primary_key=True)
    squad_push_id = db.Column(db.Integer, db.ForeignKey('squad_pushes.id'), nullable=False, index=True)

    player_id = db.Column(db.Integer, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name  = db.Column(db.String(100), nullable=False)
    number     = db.Column(db.Integer, nullable=True)
    is_goalkeeper = db.Column(db.Boolean, nullable=False, default=False)

    role = db.Column(db.String(10), nullable=False, default=ROLE_NONE)

    def __repr__(self) -> str:
        return f'<SquadPushPlayer {self.last_name} {self.first_name} role={self.role}>'
