"""Commentator — moduł futsal_nalf.

Dziedziczy BaseCommentatorMixin z core bez rozszerzeń.
"""
from core.models.base_commentator import BaseCommentatorMixin
from core.extensions import db

class Commentator(BaseCommentatorMixin, db.Model):
    __tablename__ = 'commentators'
