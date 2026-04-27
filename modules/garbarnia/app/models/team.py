"""Team — moduł garbarnia.

Rozszerza BaseTeamMixin o:
  - coach (trener drużyny)
"""
from core.extensions import db
from core.models.base_team import BaseTeamMixin


class Team(BaseTeamMixin, db.Model):
    __tablename__ = 'teams'

    coach = db.Column(db.String(100), nullable=True)

    def to_dict(self):
        d = super().to_dict()
        d['coach'] = self.coach
        return d
