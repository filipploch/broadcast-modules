from core.extensions import db
from core.models.base_league import BaseLeagueMixin

class League(BaseLeagueMixin, db.Model):
    __tablename__ = 'leagues'

    games_url   = db.Column(db.String(500), nullable=True)

    table_url   = db.Column(db.String(500), nullable=True)

    scorers_url = db.Column(db.String(500), nullable=True)

    assists_url = db.Column(db.String(500), nullable=True)

    canadian_url = db.Column(db.String(500), nullable=True)
