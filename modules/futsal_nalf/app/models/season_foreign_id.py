from core.extensions import db
from core.models.base_season_foreign_id import BaseSeasonForeignIdMixin


class SeasonForeignId(BaseSeasonForeignIdMixin, db.Model):
    __tablename__ = 'season_foreign_ids'
