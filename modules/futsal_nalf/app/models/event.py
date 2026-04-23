"""Event — moduł futsal_nalf.

Dziedziczy BaseEventMixin z core bez rozszerzeń.
"""
from core.models.base_event import BaseEventMixin
from core.extensions import db

class Event(BaseEventMixin, db.Model):
    __tablename__ = 'events'
