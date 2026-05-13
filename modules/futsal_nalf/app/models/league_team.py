"""LeagueTeam — moduł futsal-nalf.

Dziedziczy BaseLeagueTeamMixin z core bez rozszerzeń.
"""
from core.models.base_league_team import BaseLeagueTeamMixin
from core.extensions import db


class LeagueTeam(BaseLeagueTeamMixin, db.Model):
    __tablename__ = 'league_teams'
