"""GameReferee — moduł garbarnia.

Dziedziczy BaseGameRefereeMixin z core bez rozszerzeń.
"""
from core.models.base_game_referee import BaseGameRefereeMixin
from core.extensions import db

class GameReferee(BaseGameRefereeMixin, db.Model):
    __tablename__ = 'game_referees'
