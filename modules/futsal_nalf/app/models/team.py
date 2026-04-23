from core.extensions import db
from core.models.base_team import BaseTeamMixin

class Team(BaseTeamMixin, db.Model):
    __tablename__ = 'teams'

    team_url = db.Column(db.String(500), nullable=True)
