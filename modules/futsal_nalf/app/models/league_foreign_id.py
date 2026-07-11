from core.extensions import db
from core.models.base_league_foreign_id import BaseLeagueForeignIdMixin


class LeagueForeignId(BaseLeagueForeignIdMixin, db.Model):
    __tablename__ = 'league_foreign_ids'
