"""Team model — moduł futsal-nalf.

Dziedziczy BaseTeam z core i dodaje:
  - team_url (link do profilu na nalffutsal.pl)
"""
from core.extensions import db
from core.models.base_team import BaseTeam


class Team(BaseTeam):
    """Drużyna futsalowa."""
    __tablename__ = 'teams'

    # ── Futsal-specific ───────────────────────────────────────────────────────
    team_url = db.Column(db.String(500), nullable=True)

    def to_dict(self):
        d = super().to_dict()
        d['team_url'] = self.team_url
        return d
