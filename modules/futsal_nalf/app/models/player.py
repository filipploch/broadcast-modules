"""Player model — moduł futsal-nalf.

Dziedziczy BasePlayer z core i dodaje pola specyficzne dla futsalu:
  - is_goalkeeper
  - is_captain
"""
from core.extensions import db
from core.models.base_player import BasePlayer


class Player(BasePlayer):
    """Zawodnik futsalowy."""
    __tablename__ = 'players'

    # ── Futsal-specific ───────────────────────────────────────────────────────
    is_goalkeeper = db.Column(db.Boolean, default=False, nullable=False)
    is_captain    = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def display_name(self):
        name = self.full_name
        indicators = []
        if self.is_captain:
            indicators.append("(C)")
        if self.is_goalkeeper:
            indicators.append("(GK)")
        if indicators:
            name += " " + " ".join(indicators)
        return name

    def to_dict(self):
        d = super().to_dict()
        d.update({
            'is_goalkeeper': self.is_goalkeeper,
            'is_captain':    self.is_captain,
            'display_name':  self.display_name,
        })
        return d
