"""TeamManager — moduł futsal-nalf.

Rozszerza CoreTeamManager o obsługę pola team_url specyficznego
dla modelu Team w futsal-nalf.
"""
from core.managers.team_manager import TeamManager as _CoreTeamManager
from app.models.team import Team
import logging

logger = logging.getLogger(__name__)


class TeamManager(_CoreTeamManager):

    def get_team_by_url(self, team_url: str):
        """Wyszukuje drużynę po team_url (pole specyficzne dla futsal-nalf)."""
        return Team.query.filter_by(team_url=team_url).first()

    def create_team(self, name, name_14, short_name,
                    team_url=None, logo_path='static/images/logos/default.png',
                    uniform=None):
        """Nadpisuje metodę core — dodaje parametr team_url."""
        team = super().create_team(
            name=name, name_14=name_14, short_name=short_name,
            logo_path=logo_path, uniform=uniform,
        )
        if team_url is not None:
            team.team_url = team_url
            from core.extensions import db
            db.session.commit()
        return team

    def update_team(self, team_id: int, **kwargs):
        """Nadpisuje metodę core — wydziela team_url przed przekazaniem do super()."""
        team_url = kwargs.pop('team_url', None)
        team = super().update_team(team_id, **kwargs)
        if team is None:
            return None
        if team_url is not None:
            team.team_url = team_url
            from core.extensions import db
            db.session.commit()
        return team