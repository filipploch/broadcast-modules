"""GamePlayer — moduł garbarnia.

Rozszerza BaseGamePlayerMixin o pola specyficzne dla piłki nożnej:
  - is_goalkeeper, is_captain  (snapshot z chwili przypisania)
  - is_youth                   (snapshot; zmiana synchronizowana z Player)
  - role                       ('starter' | 'substitute' | 'retired')
"""
from core.extensions import db
from core.models.base_game_player import BaseGamePlayerMixin

ROLE_STARTER    = 'starter'
ROLE_SUBSTITUTE = 'substitute'
ROLE_RETIRED    = 'retired'
VALID_ROLES     = (ROLE_STARTER, ROLE_SUBSTITUTE, ROLE_RETIRED)


class GamePlayer(BaseGamePlayerMixin, db.Model):
    __tablename__ = 'game_players'

    is_goalkeeper = db.Column(db.Boolean, default=False, nullable=False)
    is_captain    = db.Column(db.Boolean, default=False, nullable=False)
    is_youth      = db.Column(db.Boolean, default=False, nullable=False)
    role          = db.Column(db.String(20), default=ROLE_STARTER, nullable=False)

    def to_dict(self):
        d = super().to_dict()
        d['is_goalkeeper'] = self.is_goalkeeper
        d['is_captain']    = self.is_captain
        d['is_youth']      = self.is_youth
        d['role']          = self.role
        return d
