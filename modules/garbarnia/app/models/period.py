"""Period — moduł futsal-nalf.

Rozszerza BasePeriod o pola specyficzne dla futsalu:
  - home_team_fouls, away_team_fouls (faule liczone per połowa, reset po 5)
"""
from core.extensions import db
from core.models.base_period import BasePeriod
from datetime import datetime


class Period(BasePeriod):
    __tablename__ = 'periods'

    # ── Futsal-specific ───────────────────────────────────────────────────────
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

    def sync_to_game(self):
        """Rozszerza BasePeriod.sync_to_game — synchronizuje też faule."""
        from core.extensions import db as _db
        game = self.game
        if not game:
            return
        all_periods = Period.query.filter_by(game_id=self.game_id).all()
        game.home_team_goals = sum(p.home_team_goals for p in all_periods)
        game.away_team_goals = sum(p.away_team_goals for p in all_periods)
        current = game.get_current_period()
        ref = current if current else self
        game.home_team_fouls = ref.home_team_fouls
        game.away_team_fouls = ref.away_team_fouls
        game.updated_at = datetime.utcnow()
        _db.session.commit()

    def to_dict(self):
        d = super().to_dict()
        d.update({
            'home_team_fouls': self.home_team_fouls,
            'away_team_fouls': self.away_team_fouls,
        })
        return d
