"""BaseGamePlayer — abstrakcyjna klasa bazowa dla przypisania zawodnika do meczu.

Przechowuje snapshot atrybutów zawodnika z chwili przypisania
(numer, pozycja itp.) — chroni dane historyczne gdy zawodnik zmieni drużynę.

Pola wspólne dla wszystkich dyscyplin:
  - player_id, game_id, team_id
  - number (numer koszulki w tym meczu)

Pola specyficzne dla dyscypliny (np. is_goalkeeper, is_captain w futsalu)
dodawane są w klasie GamePlayer konkretnego modułu.
"""
from core.extensions import db
from datetime import datetime


class BaseGamePlayer(db.Model):
    __abstract__ = True

    id     = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    @db.declared_attr
    def player_id(cls):
        return db.Column(db.Integer, db.ForeignKey('players.id'),
                         nullable=False, index=True)

    @db.declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'),
                         nullable=False, index=True)

    @db.declared_attr
    def team_id(cls):
        return db.Column(db.Integer, db.ForeignKey('teams.id'),
                         nullable=False, index=True)




    @db.declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('player_id', 'game_id', name='unique_game_player'),
        )

    def __repr__(self):
        return (f'<GamePlayer player_id={self.player_id} '
                f'game_id={self.game_id} team_id={self.team_id}>')

    def to_squad_dict(self):
        return {
            'id':         self.player_id,
            'first_name': self.player.first_name if self.player else None,
            'last_name':  self.player.last_name  if self.player else None,
            'number':     self.number,
        }

    def to_dict(self):
        return {
            'id':              self.id,
            'player_id':       self.player_id,
            'player_name':     self.player.full_name if self.player else None,
            'game_id':         self.game_id,
            'team_id':         self.team_id,
            'team_name':       self.team.name        if self.team   else None,
            'team_name_14':    self.team.name_14      if self.team   else None,
            'team_short_name': self.team.short_name   if self.team   else None,
            'number':          self.number,
            'created_at':      self.created_at.isoformat() if self.created_at else None,
            'updated_at':      self.updated_at.isoformat() if self.updated_at else None,
        }
