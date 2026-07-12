from core.extensions import db
from core.models.base_pending_player_departure import BasePendingPlayerDepartureMixin


class PendingPlayerDeparture(BasePendingPlayerDepartureMixin, db.Model):
    __tablename__ = 'pending_player_departures'
