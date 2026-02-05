"""LeagueTeam model - Many-to-many relationship between leagues and teams"""
from app.extensions import db
from datetime import datetime


class LeagueTeam(db.Model):
    """Junction table: Teams participating in leagues"""
    __tablename__ = 'league_teams'

    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)
    group_nr = db.Column(db.Integer, nullable=False, default=1)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships defined via backref in League and Team models

    # Composite unique constraint: each team can be in league only once
    __table_args__ = (
        db.UniqueConstraint('league_id', 'team_id', name='uix_league_team'),
        db.Index('ix_league_group', 'league_id', 'group_nr'),
    )

    def __repr__(self):
        return f'<LeagueTeam league_id={self.league_id} team_id={self.team_id} group={self.group_nr}>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'league_id': self.league_id,
            'league_name': self.league.name if self.league else None,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'team_short_name': self.team.short_name if self.team else None,
            'group_nr': self.group_nr,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }