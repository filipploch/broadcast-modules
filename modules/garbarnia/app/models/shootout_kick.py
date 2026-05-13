"""ShootoutKick — moduł garbarnia.

Dziedziczy BaseShootoutKickMixin z core bez rozszerzeń.
"""
from core.models.base_shootout_kick import BaseShootoutKickMixin
from core.extensions import db

class ShootoutKick(BaseShootoutKickMixin, db.Model):
    __tablename__ = 'shootout_kicks'
