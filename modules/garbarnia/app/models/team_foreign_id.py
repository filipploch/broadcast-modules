from core.extensions import db
from core.models.base_team_foreign_id import BaseTeamForeignIdMixin


class TeamForeignId(BaseTeamForeignIdMixin, db.Model):
    __tablename__ = 'team_foreign_ids'
