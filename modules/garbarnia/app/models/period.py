"""Period — moduł garbarnia.

Rozszerza BasePeriodMixin o licznik fauli (futbol: max 5 fauli na połowę).
"""
from core.extensions import db
from core.models.base_period import BasePeriodMixin
from datetime import datetime


class Period(BasePeriodMixin, db.Model):
    __tablename__ = 'periods'

    home_team_fouls = db.Column(db.Integer, default=0, nullable=False)
    away_team_fouls = db.Column(db.Integer, default=0, nullable=False)

    def update_fouls(self, home_fouls, away_fouls):
        self.home_team_fouls = home_fouls
        self.away_team_fouls = away_fouls
        self.updated_at = datetime.utcnow()

    def increment_home_fouls(self, value: int):
        new_val = self.home_team_fouls + value
        if 0 <= new_val <= 5:
            self.home_team_fouls = new_val
            self.updated_at = datetime.utcnow()

    def increment_away_fouls(self, value: int):
        new_val = self.away_team_fouls + value
        if 0 <= new_val <= 5:
            self.away_team_fouls = new_val
            self.updated_at = datetime.utcnow()
