from core.extensions import db
from core.models.base_game import BaseGameMixin
from datetime import datetime

class Game(BaseGameMixin, db.Model):
    __tablename__ = 'games'

    home_team_fouls = db.Column(db.Integer, nullable=False, default=0)

    away_team_fouls = db.Column(db.Integer, nullable=False, default=0)

    is_home_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)

    is_away_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)

    shootout = db.relationship('Shootout', backref='game',
                               uselist=False, cascade='all, delete-orphan')

    def to_dict(self):
        d = super().to_dict()
        d['home_team_fouls']         = self.home_team_fouls
        d['away_team_fouls']         = self.away_team_fouls
        d['is_home_team_lost_by_wo'] = self.is_home_team_lost_by_wo
        d['is_away_team_lost_by_wo'] = self.is_away_team_lost_by_wo
        d['is_walkover']             = self.is_walkover
        d['is_double_walkover']      = self.is_double_walkover
        d['has_shootout']            = self.has_shootout
        d['full_score_string']       = self.full_score_string
        d['shootout']                = self.shootout.to_dict() if self.shootout else None
        return d