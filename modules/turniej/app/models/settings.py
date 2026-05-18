"""Settings — moduł turniej.

Dziedziczy BaseSettingsMixin. Bez pól shootout.
"""
from core.extensions import db
from core.models.base_settings import BaseSettingsMixin


class Settings(BaseSettingsMixin, db.Model):
    __tablename__ = 'settings'

    current_shootout_id = db.Column(db.Integer, db.ForeignKey('shootouts.id'), nullable=True)

    current_season   = db.relationship('Season',   foreign_keys='Settings.current_season_id')
    current_game     = db.relationship('Game',     foreign_keys='Settings.current_game_id')
    current_period   = db.relationship('Period',   foreign_keys='Settings.current_period_id')
    current_shootout = db.relationship('Shootout', foreign_keys='Settings.current_shootout_id')

    @classmethod
    def set_current_shootout(cls, shootout_id):
        s = cls.get_settings()
        s.current_shootout_id = shootout_id
        db.session.commit()
