from core.extensions import db
from core.models.base_game_conflict import BaseGameConflictMixin


class GameConflict(BaseGameConflictMixin, db.Model):
    __tablename__ = 'game_conflicts'
