"""GameCommentator — moduł futsal_nalf.

Dziedziczy BaseGameCommentatorMixin z core bez rozszerzeń.
"""
from core.models.base_game_commentator import BaseGameCommentatorMixin
from core.extensions import db

class GameCommentator(BaseGameCommentatorMixin, db.Model):
    __tablename__ = 'game_commentators'
