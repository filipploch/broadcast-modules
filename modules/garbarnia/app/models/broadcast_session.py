"""BroadcastSession, SessionGame — sesja transmisji i mecz w sesji (E1). Logika w core/managers/session_manager.py."""
from core.extensions import db
from core.models.base_broadcast_session import BaseBroadcastSessionMixin, BaseSessionGameMixin


class BroadcastSession(BaseBroadcastSessionMixin, db.Model):
    __tablename__ = 'broadcast_sessions'


class SessionGame(BaseSessionGameMixin, db.Model):
    __tablename__ = 'session_games'
