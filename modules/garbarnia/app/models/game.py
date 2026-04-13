"""Game model — moduł futsal-nalf.

Dziedziczy BaseGame z core i dodaje pola specyficzne dla futsalu:
  - home_team_fouls, away_team_fouls
  - walkover (is_home/away_team_lost_by_wo)
  - relacja do Shootout
"""
from core.extensions import db
from core.models.base_game import BaseGame
from datetime import datetime


class Game(BaseGame):
    """Mecz futsalowy."""
    __tablename__ = 'games'

    # ── Futsal-specific ───────────────────────────────────────────────────────
    home_team_fouls = db.Column(db.Integer, nullable=False, default=0)
    away_team_fouls = db.Column(db.Integer, nullable=False, default=0)

    is_home_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)
    is_away_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)

    # Relacja do rzutów karnych (tylko futsal)
    shootout = db.relationship('Shootout', backref='game',
                               uselist=False, cascade='all, delete-orphan')

    # ── Właściwości futsal-specific ───────────────────────────────────────────

    @property
    def is_walkover(self):
        return self.is_home_team_lost_by_wo or self.is_away_team_lost_by_wo

    @property
    def is_double_walkover(self):
        return self.is_home_team_lost_by_wo and self.is_away_team_lost_by_wo

    @property
    def has_shootout(self):
        return self.shootout is not None

    @property
    def full_score_string(self):
        base = self.score_string
        if self.has_shootout:
            return f"{base} k. {self.shootout.score_string}"
        return base

    def update_fouls(self, home_fouls, away_fouls):
        self.home_team_fouls = home_fouls
        self.away_team_fouls = away_fouls
        self.updated_at = datetime.utcnow()

    def set_home_walkover_loss(self):
        self.is_home_team_lost_by_wo = True
        self.updated_at = datetime.utcnow()

    def set_away_walkover_loss(self):
        self.is_away_team_lost_by_wo = True
        self.updated_at = datetime.utcnow()

    def set_double_walkover(self):
        self.is_home_team_lost_by_wo = True
        self.is_away_team_lost_by_wo = True
        self.updated_at = datetime.utcnow()

    def clear_walkovers(self):
        self.is_home_team_lost_by_wo = False
        self.is_away_team_lost_by_wo = False
        self.updated_at = datetime.utcnow()

    def get_shootout_winner_id(self):
        if self.has_shootout:
            return self.shootout.winner_id
        return None

    def get_team_stats(self, team_id, include_live=False):
        """Nadpisuje BaseGame — uwzględnia walkover."""
        if not include_live and not self.is_finished:
            return None
        if include_live and not (self.is_finished or self.is_live):
            return None
        if team_id not in [self.home_team_id, self.away_team_id]:
            return None

        stats = {'games': 1, 'points': 0, 'wins': 0, 'draws': 0,
                 'loses': 0, 'goals_scored': 0, 'goals_lost': 0}

        is_home = (team_id == self.home_team_id)
        team_goals     = self.home_team_goals if is_home else self.away_team_goals
        opponent_goals = self.away_team_goals if is_home else self.home_team_goals
        team_wo     = self.is_home_team_lost_by_wo if is_home else self.is_away_team_lost_by_wo
        opponent_wo = self.is_away_team_lost_by_wo if is_home else self.is_home_team_lost_by_wo

        if self.is_double_walkover:
            stats['loses'] = 1; stats['points'] = -1
            stats['goals_lost'] = self.WALKOVER_SCORE
            return stats
        if team_wo:
            stats['loses'] = 1; stats['points'] = -1
            stats['goals_lost'] = self.WALKOVER_SCORE
            return stats
        if opponent_wo:
            stats['wins'] = 1; stats['points'] = 3
            stats['goals_scored'] = self.WALKOVER_SCORE
            return stats

        if team_goals is not None and opponent_goals is not None:
            stats['goals_scored'] = team_goals
            stats['goals_lost']   = opponent_goals
            if team_goals > opponent_goals:
                stats['wins'] = 1; stats['points'] = 3
            elif team_goals == opponent_goals:
                stats['draws'] = 1; stats['points'] = 1
            else:
                stats['loses'] = 1

        return stats
    
    def get_squad(self, team_id):
        """
        Return players assigned to this game grouped by team side.

        Returns:
            [GamePlayer.to_dict(), ...]
        Ordered per team: goalkeepers first, then by number asc (nulls last), then last_name.
        """
        from app.models.player import Player

        def _sorted(team_id):
            from app.models.game_player import GamePlayer
            return (
                self.game_players
                .filter_by(team_id=team_id)
                .join(Player, GamePlayer.player_id == Player.id)
                .order_by(
                    GamePlayer.is_goalkeeper.desc(),
                    GamePlayer.number.asc().nullslast(),
                    Player.last_name.asc(),
                )
                .all()
            )
        return [gp.to_dict() for gp in _sorted(team_id)]
