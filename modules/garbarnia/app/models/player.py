"""Player — moduł football (laczynaspilka.pl).

Rozszerza BasePlayer o pola specyficzne dla piłki nożnej PZPN:
  - is_youth: czy zawodnik jest młodzieżowcem (U21 w rozumieniu ekstraklasy,
              lub inny próg zdefiniowany przez ligę)
"""
from core.extensions import db
from core.models.base_player import BasePlayer


class Player(BasePlayer):
    __tablename__ = 'players'

    # ── Football-specific ─────────────────────────────────────────────────────
    is_goalkeeper = db.Column(db.Boolean, default=False, nullable=False)
    is_captain    = db.Column(db.Boolean, default=False, nullable=False)
    is_youth      = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def display_name(self):
        name = self.full_name
        indicators = []
        if self.is_captain:
            indicators.append("(C)")
        if self.is_goalkeeper:
            indicators.append("(GK)")
        if self.is_youth:
            indicators.append("(M)")
        if indicators:
            name += " " + " ".join(indicators)
        return name

    def to_dict(self):
        d = super().to_dict()
        d.update({
            'is_goalkeeper': self.is_goalkeeper,
            'is_captain':    self.is_captain,
            'is_youth':      self.is_youth,
        })
        return d
