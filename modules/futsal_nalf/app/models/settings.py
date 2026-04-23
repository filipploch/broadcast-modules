"""Settings — moduł futsal-nalf.

Rozszerza BaseSettingsMixin o:
  - current_shootout_id (FK do shootouts)
  - relację current_shootout
"""
from core.extensions import db
from core.models.base_settings import BaseSettingsMixin


class Settings(BaseSettingsMixin, db.Model):
    __tablename__ = 'settings'

    current_season = db.relationship('Season',
                                     foreign_keys='Settings.current_season_id')
    current_game   = db.relationship('Game',
                                     foreign_keys='Settings.current_game_id')
    current_period = db.relationship('Period',
                                     foreign_keys='Settings.current_period_id')

    # futsal_nalf dodatkowo:
    current_shootout_id = db.Column(db.Integer,
                                    db.ForeignKey('shootouts.id'), nullable=True)
    current_shootout = db.relationship('Shootout',
                                       foreign_keys='Settings.current_shootout_id',
                                       backref='settings_ref')

    @classmethod
    def set_current_shootout(cls, shootout_id):
        s = cls.get_settings()
        s.current_shootout_id = shootout_id
        from core.extensions import db as _db
        from datetime import datetime
        s.updated_at = datetime.utcnow()
        _db.session.commit()

    @classmethod
    def get_current_shootout(cls):
        s = cls.get_settings()
        if s.current_shootout_id is None:
            return None
        from app.models.shootout import Shootout
        return Shootout.query.get(s.current_shootout_id)
