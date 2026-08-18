"""HelperSquadProposal — moduł garbarnia.

Propozycja składu (wyjściowa jedenastka / rezerwa) i trenera, przesłana przez
pomocnika z Helper App. To atomowa "paczka" (nie strumień pojedynczych
zdarzeń jak `HelperEventCandidate`), więc jedna tabela wystarcza — lista
graczy trzymana jako JSON, bez potrzeby dedupu per-gracz.

Kanał transportowy: lekki REST (nie WSS relay) — patrz
`app/managers/helper_squad_client.py`.
"""
import json

from core.extensions import db
from datetime import datetime

STATUS_PENDING  = 'pending'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'
VALID_STATUSES  = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)


class HelperSquadProposal(db.Model):
    __tablename__ = 'helper_squad_proposals'

    id      = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)
    helper_id = db.Column(db.Integer, db.ForeignKey('helpers.id'), nullable=True)

    # id SquadPush z Helper App — dedup przy re-fetch w oknie retry (patrz
    # HelperSquadClient.fetch_proposals()).
    remote_squad_push_id = db.Column(db.Integer, nullable=False, unique=True, index=True)

    coach_name = db.Column(db.String(100), nullable=True)
    # JSON: [{"player_id": int, "role": "starter"|"substitute"|"none"}, ...]
    players_json = db.Column(db.Text, nullable=False, default='[]')

    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)

    submitted_at = db.Column(db.DateTime, nullable=True)
    resolved_at  = db.Column(db.DateTime, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    game   = db.relationship('Game', foreign_keys=[game_id])
    team   = db.relationship('Team', foreign_keys=[team_id])
    helper = db.relationship('Helper', foreign_keys=[helper_id])

    @property
    def players(self):
        return json.loads(self.players_json or '[]')

    @players.setter
    def players(self, value):
        self.players_json = json.dumps(value or [])

    def __repr__(self):
        return (f'<HelperSquadProposal id={self.id} game_id={self.game_id} '
                f'team_id={self.team_id} status={self.status}>')
