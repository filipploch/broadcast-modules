from core.models.base_game_event import BaseGameEventMixin
from core.extensions import db

class GameEvent(BaseGameEventMixin, db.Model):
    __tablename__ = 'game_events'
