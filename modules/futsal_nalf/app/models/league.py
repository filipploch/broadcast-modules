"""League model — moduł futsal-nalf.

Dziedziczy BaseLeague z core i dodaje:
  - URLs do zasobów zewnętrznych nalffutsal.pl
"""
from core.extensions import db
from core.models.base_league import BaseLeague


class League(BaseLeague):
    """Liga NALF Futsal."""
    __tablename__ = 'leagues'

    # ── NALF-specific ─────────────────────────────────────────────────────────
    games_url   = db.Column(db.String(500), nullable=True)
    table_url   = db.Column(db.String(500), nullable=True)
    scorers_url = db.Column(db.String(500), nullable=True)
    assists_url = db.Column(db.String(500), nullable=True)
    canadian_url = db.Column(db.String(500), nullable=True)

    def to_dict(self):
        d = super().to_dict()
        d.update({
            'games_url':    self.games_url,
            'table_url':    self.table_url,
            'scorers_url':  self.scorers_url,
            'assists_url':  self.assists_url,
            'canadian_url': self.canadian_url,
        })
        return d
