"""Settings — moduł garbarnia.

Ustawienia aplikacji (core/models/base_settings.py). Od E1 bez wskaźnika meczu/okresu/sezonu/serii karnych:
te dane wynikają z sesji transmisji (core/managers/session_manager.py).
"""
from core.extensions import db
from core.models.base_settings import BaseSettingsMixin


class Settings(BaseSettingsMixin, db.Model):
    __tablename__ = 'settings'

    browse_season = db.relationship('Season', foreign_keys='Settings.browse_season_id')
