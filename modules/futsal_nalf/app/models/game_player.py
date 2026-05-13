from core.extensions import db
from core.models.base_game_player import BaseGamePlayerMixin

class GamePlayer(BaseGamePlayerMixin, db.Model):
    __tablename__ = 'game_players'

    is_goalkeeper = db.Column(db.Boolean, default=False, nullable=False)

    is_captain    = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        d = super().to_dict()
        d['is_goalkeeper'] = self.is_goalkeeper
        d['is_captain']    = self.is_captain
        return d