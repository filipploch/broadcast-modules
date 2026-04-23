"""Player — moduł garbarnia.

Rozszerza BasePlayerMixin o pola specyficzne dla piłki nożnej PZPN:
  - is_goalkeeper
  - is_captain
  - is_youth (U21 lub inny próg zdefiniowany przez ligę)
"""
from core.extensions import db
from core.models.base_player import BasePlayerMixin


class Player(BasePlayerMixin, db.Model):
    __tablename__ = 'players'

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
        d['is_goalkeeper'] = self.is_goalkeeper
        d['is_captain']    = self.is_captain
        d['is_youth']      = self.is_youth
        return d
