"""Season — moduł futsal_nalf.

Dziedziczy BaseSeasonMixin z core bez rozszerzeń.
"""
from core.models.base_season import BaseSeasonMixin
from core.extensions import db

class Season(BaseSeasonMixin, db.Model):
    __tablename__ = 'seasons'
