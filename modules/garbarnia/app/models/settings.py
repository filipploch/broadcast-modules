"""Settings — moduł futsal-nalf.

Rozszerza BaseSettings o pole specyficzne dla futsalu:
  - current_shootout_id (aktywny konkurs rzutów karnych)
"""
from core.extensions import db
from core.models.base_settings import BaseSettings


class Settings(BaseSettings):
    __tablename__ = 'settings'

    # FK z constraintami — nadpisują kolumny z BaseSettings (bez FK)
    current_season_id = db.Column(db.Integer, db.ForeignKey('seasons.id'), nullable=True)
    current_game_id   = db.Column(db.Integer, db.ForeignKey('games.id'),   nullable=True)
    current_period_id = db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=True)

    # ── Futsal-specific ───────────────────────────────────────────────────────
    current_shootout_id = db.Column(db.Integer,
                                    db.ForeignKey('shootouts.id'), nullable=True)

    current_season  = db.relationship('Season',   foreign_keys=[current_season_id],
                                      backref='settings_ref')
    current_game    = db.relationship('Game',     foreign_keys=[current_game_id],
                                      backref='settings_ref')
    current_period  = db.relationship('Period',   foreign_keys=[current_period_id],
                                      backref='settings_ref')
    current_shootout = db.relationship('Shootout', foreign_keys=[current_shootout_id],
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
