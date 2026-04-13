"""GamePlayer — moduł futsal-nalf.

Rozszerza BaseGamePlayer o pola specyficzne dla futsalu:
  - is_goalkeeper, is_captain (snapshot z chwili przypisania)
"""
from core.extensions import db
from core.models.base_game_player import BaseGamePlayer


class GamePlayer(BaseGamePlayer):
    __tablename__ = 'game_players'

    # ── Futsal-specific ───────────────────────────────────────────────────────
    is_goalkeeper = db.Column(db.Boolean, default=False, nullable=False)
    is_captain    = db.Column(db.Boolean, default=False, nullable=False)

    def to_squad_dict(self):
        d = super().to_squad_dict()
        d.update({
            'is_goalkeeper': self.is_goalkeeper,
            'is_captain':    self.is_captain,
        })
        return d

    def to_dict(self):
        d = super().to_dict()
        d.update({
            'is_goalkeeper': self.is_goalkeeper,
            'is_captain':    self.is_captain,
        })
        return d
