from core.extensions import db
from core.models.base_pending_player_match import BasePendingPlayerMatchMixin


class PendingPlayerMatch(BasePendingPlayerMatchMixin, db.Model):
    __tablename__ = 'pending_player_matches'
