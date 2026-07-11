"""TeamManager — moduł garbarnia.

Rozszerza CoreTeamManager o obsługę pola coach specyficznego
dla modelu Team w garbarni.
"""
from core.managers.team_manager import TeamManager as _CoreTeamManager
from app.models.team import Team
import logging

logger = logging.getLogger(__name__)


class TeamManager(_CoreTeamManager):

    def create_team(self, name: str, name_14: str, short_name: str,
                logo_path: str = 'static/images/logos/default.png',
                coach: str = None, uniform: dict = None):
        """Nadpisuje metodę core — dodaje parametr coach."""
        team = super().create_team(
            name=name, name_14=name_14, short_name=short_name,
            logo_path=logo_path, uniform=uniform,
        )
        if coach is not None:
            team.coach = coach
            from core.extensions import db
            db.session.commit()
        return team

    def update_team(self, team_id: int, **kwargs):
        """Nadpisuje metodę core — wydziela coach przed przekazaniem do super()."""
        coach = kwargs.pop('coach', None)
        team = super().update_team(team_id, **kwargs)
        if team is None:
            return None
        if coach is not None:
            team.coach = coach
            from core.extensions import db
            db.session.commit()
        return team