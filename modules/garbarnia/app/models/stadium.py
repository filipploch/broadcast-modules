"""Stadium — moduł garbarnia.

Dziedziczy BaseStadiumMixin z core bez rozszerzeń.
"""
from core.models.base_stadium import BaseStadiumMixin
from core.extensions import db

class Stadium(BaseStadiumMixin, db.Model):
    __tablename__ = 'stadiums'