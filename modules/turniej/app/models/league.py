from core.extensions import db
from core.models.base_league import BaseLeagueMixin

class League(BaseLeagueMixin, db.Model):
    __tablename__ = 'leagues'

    foreign_id = None
