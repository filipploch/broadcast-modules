"""Substitution — zmiana zawodnika w meczu (moduł garbarnia).

Kolumny:
  game_id            — FK do games.id
  period_id          — FK do periods.id (w której połowie nastąpiła zmiana)
  game_time_ms       — czas meczu w ms odczytany z timer-plugin (lub podany ręcznie)
  team_id            — FK do teams.id
  player_in_id       — FK do players.id  — zawodnik wchodzący (z ławki na boisko)
  player_out_id      — FK do players.id  — zawodnik schodzący (z boiska na ławkę)
  substitution_group — int grupujący zmiany wielokrotne wykonane w tej samej chwili;
                       wszystkie zmiany w grupie mają ten sam game_time_ms
"""
from core.extensions import db
from datetime import datetime


class Substitution(db.Model):
    __tablename__ = 'substitutions'

    id                 = db.Column(db.Integer, primary_key=True)
    substitution_group = db.Column(db.Integer, nullable=False)
    game_time_ms       = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    # ── FK ────────────────────────────────────────────────────────────────────
    game_id   = db.Column(db.Integer, db.ForeignKey('games.id'),
                          nullable=False, index=True)
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id'),
                          nullable=True, index=True)
    team_id   = db.Column(db.Integer, db.ForeignKey('teams.id'),
                          nullable=False, index=True)

    # Używamy players.id bezpośrednio (nie game_players.id),
    # bo player_in_id i player_out_id to stałe referencje do zawodników.
    player_in_id  = db.Column(db.Integer, db.ForeignKey('players.id'),
                               nullable=False, index=True)
    player_out_id = db.Column(db.Integer, db.ForeignKey('players.id'),
                               nullable=False, index=True)

    # ── Relacje ───────────────────────────────────────────────────────────────
    game      = db.relationship('Game',   backref=db.backref('substitutions', lazy='dynamic'))
    period    = db.relationship('Period', backref=db.backref('substitutions', lazy='dynamic'))
    team      = db.relationship('Team',   backref=db.backref('substitutions', lazy='dynamic'))
    player_in  = db.relationship('Player', foreign_keys=[player_in_id],
                                 backref=db.backref('substitutions_in',  lazy='dynamic'))
    player_out = db.relationship('Player', foreign_keys=[player_out_id],
                                 backref=db.backref('substitutions_out', lazy='dynamic'))

    def __repr__(self):
        return (f'<Substitution id={self.id} game={self.game_id} '
                f'group={self.substitution_group} '
                f'in={self.player_in_id} out={self.player_out_id}>')

    def to_dict(self):
        return {
            'id':                 self.id,
            'substitution_group': self.substitution_group,
            'game_time_ms':       self.game_time_ms,
            'game_id':            self.game_id,
            'period_id':          self.period_id,
            'team_id':            self.team_id,
            'team_short_name':    self.team.short_name,
            'player_in_id':       self.player_in_id,
            'player_in_name':     self.player_in.full_name  if self.player_in  else None,
            'player_in_number':   self.player_in.number     if self.player_in  else None,
            'player_out_id':      self.player_out_id,
            'player_out_name':    self.player_out.full_name if self.player_out else None,
            'player_out_number':  self.player_out.number   if self.player_out else None,
            'created_at':         self.created_at.isoformat() if self.created_at else None,
            'updated_at':         self.updated_at.isoformat() if self.updated_at else None,
        }
