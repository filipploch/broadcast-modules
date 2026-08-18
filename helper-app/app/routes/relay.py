"""relay — lekki kanał REST wywoływany wychodząco przez moduł główny.

Osobny od przyszłego WSS relay (docs/helper-app-design.md w repo modułu
głównego) — moduł główny zawsze inicjuje żądanie (POST push kadry, GET pull
propozycji), bo Render nie może połączyć się z modułem głównym (ten jest za
NAT-em). Autentykacja: `Authorization: Bearer <HELPER_APP_REST_TOKEN>`.
"""
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import SquadPush, SquadPushPlayer

relay_bp = Blueprint('relay', __name__, url_prefix='/api/relay')

# Okno, w którym GET /squad/proposals nadal zwraca już raz pobrane
# zgłoszenia — zabezpieczenie przed utratą propozycji, gdyby moduł główny
# padł między odpowiedzią GET a lokalnym zapisem.
_RETRY_WINDOW = timedelta(minutes=5)


def require_rest_token(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = current_app.config.get('REST_TOKEN')
        auth_header = request.headers.get('Authorization', '')
        token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
        if not expected or token != expected:
            return jsonify({'error': 'unauthorized'}), 401
        return view(*args, **kwargs)
    return wrapped


@relay_bp.route('/squad', methods=['POST'])
@require_rest_token
def receive_squad():
    """Push kadry (+ trenera) od modułu głównego.

    Merge, nie zastępowanie: jeśli dla (game_id, team_id) istnieje już
    otwarty (niewysłany) SquadPush, dopisz nowych/usuń zniknionych graczy,
    ale zachowaj już ustawione przez pomocnika role. coach_name nadpisywany
    tylko dopóki pomocnik go nie edytował (coach_name_source != 'edited').
    """
    data = request.get_json(force=True, silent=True) or {}
    game_id = data.get('game_id')
    team_id = data.get('team_id')
    if game_id is None or team_id is None:
        return jsonify({'error': 'game_id i team_id są wymagane'}), 400

    squad_push = SquadPush.query.filter_by(
        game_id=game_id, team_id=team_id, status=SquadPush.STATUS_OPEN
    ).first()

    if squad_push is None:
        squad_push = SquadPush(
            game_id=game_id,
            team_id=team_id,
            team_label=data.get('team_label'),
            coach_name=data.get('coach_name'),
            coach_name_source=SquadPush.COACH_SOURCE_PUSHED,
        )
        db.session.add(squad_push)
    else:
        squad_push.team_label = data.get('team_label') or squad_push.team_label
        if squad_push.coach_name_source != SquadPush.COACH_SOURCE_EDITED:
            squad_push.coach_name = data.get('coach_name')

    incoming = {item['player_id']: item for item in data.get('players', [])}
    existing = {p.player_id: p for p in squad_push.players}

    for player_id, sp_player in existing.items():
        if player_id not in incoming:
            db.session.delete(sp_player)

    for player_id, item in incoming.items():
        if player_id in existing:
            sp_player = existing[player_id]
            sp_player.first_name = item.get('first_name', sp_player.first_name)
            sp_player.last_name = item.get('last_name', sp_player.last_name)
            sp_player.number = item.get('number')
            sp_player.is_goalkeeper = bool(item.get('is_goalkeeper'))
            # rola NIE nadpisywana — pomocnik mógł ją już ustawić
        else:
            role = item.get('role')
            if role not in SquadPushPlayer.ROLES:
                role = SquadPushPlayer.ROLE_NONE
            db.session.add(SquadPushPlayer(
                squad_push=squad_push,
                player_id=player_id,
                first_name=item.get('first_name', ''),
                last_name=item.get('last_name', ''),
                number=item.get('number'),
                is_goalkeeper=bool(item.get('is_goalkeeper')),
                role=role,
            ))

    db.session.commit()
    return jsonify({'ok': True, 'squad_push_id': squad_push.id})


@relay_bp.route('/squad/proposals', methods=['GET'])
@require_rest_token
def list_squad_proposals():
    """Zgłoszone (status='submitted') propozycje, gotowe do pobrania przez
    moduł główny. Retry-safe: zwraca też te już raz pobrane w oknie
    `_RETRY_WINDOW` — moduł główny deduplikuje po `id` (remote_squad_push_id)."""
    now = datetime.utcnow()
    cutoff = now - _RETRY_WINDOW

    pushes = SquadPush.query.filter(
        SquadPush.status == SquadPush.STATUS_SUBMITTED,
        db.or_(SquadPush.fetched_at.is_(None), SquadPush.fetched_at > cutoff),
    ).all()

    result = []
    for sp in pushes:
        sp.fetched_at = now
        submitter = sp.submitted_by
        result.append({
            'id':                  sp.id,
            'game_id':             sp.game_id,
            'team_id':             sp.team_id,
            'coach_name':          sp.coach_name,
            'players': [
                {'player_id': p.player_id, 'role': p.role}
                for p in sp.players
            ],
            'submitted_at':        sp.submitted_at.isoformat() if sp.submitted_at else None,
            'helper_external_id':  submitter.username if submitter else None,
            'helper_display_name': submitter.display_name if submitter else None,
        })

    db.session.commit()
    return jsonify({'proposals': result})
