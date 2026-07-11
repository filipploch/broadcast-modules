from core.extensions import db
from core.models.base_pending_team_match import BasePendingTeamMatchMixin


class PendingTeamMatch(BasePendingTeamMatchMixin, db.Model):
    __tablename__ = 'pending_team_matches'
