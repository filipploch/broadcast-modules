"""BaseLeagueTeamMixin — abstrakcyjna klasa bazowa dla tabeli junction league_teams."""
from core.extensions import db
from datetime import datetime


class BaseLeagueTeamMixin:

    id       = db.Column(db.Integer, primary_key=True)
    group_nr = db.Column(db.Integer, nullable=False, default=1)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @db.declared_attr
    def league_id(cls):
        return db.Column(db.Integer, db.ForeignKey('leagues.id'),
                         nullable=False, index=True)

    @db.declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'),
                         nullable=False, index=True)

    @db.declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('league_id', 'team_id', name='uix_league_team'),
            db.Index('ix_league_group', 'league_id', 'group_nr'),
        )

    def __repr__(self):
        return (f'<LeagueTeam league_id={self.league_id} '
                f'team_id={self.team_id} group={self.group_nr}>')

    def to_dict(self):
        return {
            'id':              self.id,
            'league_id':       self.league_id,
            'league_name':     self.league.name       if self.league else None,
            'team_id':         self.team_id,
            'team_name':       self.team.name         if self.team   else None,
            'team_short_name': self.team.short_name   if self.team   else None,
            'group_nr':        self.group_nr,
            'created_at':      self.created_at.isoformat() if self.created_at else None,
        }


def get_league_team_model():
    """Zwraca klasę LeagueTeam zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'league_teams'
                and issubclass(cls, BaseLeagueTeamMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy LeagueTeam w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
