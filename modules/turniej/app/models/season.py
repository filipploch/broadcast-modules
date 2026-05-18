from core.models.base_season import BaseSeasonMixin
from core.extensions import db

class Season(BaseSeasonMixin, db.Model):
    __tablename__ = 'seasons'

    foreign_id = None
