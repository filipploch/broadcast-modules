from core.extensions import db
from core.models.base_period import BasePeriodMixin
from datetime import datetime


class Period(BasePeriodMixin, db.Model):
    __tablename__ = 'periods'

    home_team_red_cards = db.Column(db.Integer, default=0, nullable=False)
    away_team_red_cards = db.Column(db.Integer, default=0, nullable=False)
    added_time          = db.Column(db.Integer, default=0, nullable=False, server_default='0')

    def update_red_cards(self, home_red_cards, away_red_cards):
        self.home_team_red_cards = home_red_cards
        self.away_team_red_cards = away_red_cards
        self.updated_at = datetime.utcnow()

    def increment_home_red_cards(self, value: int):
        if self.home_team_red_cards + value >= 0:
            self.home_team_red_cards += value
            self.updated_at = datetime.utcnow()

    def increment_away_red_cards(self, value: int):
        if self.away_team_red_cards + value >= 0:
            self.away_team_red_cards += value
            self.updated_at = datetime.utcnow()

    def sync_to_game(self):
        from core.extensions import db as _db
        game = self.game
        if not game:
            return
        all_periods = self.__class__.query.filter_by(game_id=self.game_id).all()
        game.home_team_goals     = sum(p.home_team_goals     for p in all_periods)
        game.away_team_goals     = sum(p.away_team_goals     for p in all_periods)
        game.home_team_red_cards = sum(p.home_team_red_cards for p in all_periods)
        game.away_team_red_cards = sum(p.away_team_red_cards for p in all_periods)
        game.updated_at = datetime.utcnow()
        _db.session.commit()

    def to_dict(self):
        d = super().to_dict()
        d['home_team_red_cards'] = self.home_team_red_cards
        d['away_team_red_cards'] = self.away_team_red_cards
        d['home_team_value2']    = self.home_team_red_cards
        d['away_team_value2']    = self.away_team_red_cards
        d['added_time']          = self.added_time
        return d
