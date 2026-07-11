from core.extensions import db
from core.models.base_player_foreign_id import BasePlayerForeignIdMixin


class PlayerForeignId(BasePlayerForeignIdMixin, db.Model):
    __tablename__ = 'player_foreign_ids'
