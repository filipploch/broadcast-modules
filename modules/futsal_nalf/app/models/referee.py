"""Referee — moduł futsal_nalf.

Dziedziczy BaseRefereeMixin z core bez rozszerzeń.
"""
from core.models.base_referee import BaseRefereeMixin
from core.extensions import db

class Referee(BaseRefereeMixin, db.Model):
    __tablename__ = 'referees'
