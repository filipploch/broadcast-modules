"""EventCamera — moduł garbarnia.

Dziedziczy BaseEventCameraMixin z core bez rozszerzeń.
"""
from core.models.base_event_camera import BaseEventCameraMixin
from core.extensions import db

class EventCamera(BaseEventCameraMixin, db.Model):
    __tablename__ = 'event_cameras'
