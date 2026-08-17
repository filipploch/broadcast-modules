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
