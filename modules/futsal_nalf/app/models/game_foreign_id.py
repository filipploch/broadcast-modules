from core.extensions import db
from core.models.base_game_foreign_id import BaseGameForeignIdMixin


class GameForeignId(BaseGameForeignIdMixin, db.Model):
    __tablename__ = 'game_foreign_ids'
