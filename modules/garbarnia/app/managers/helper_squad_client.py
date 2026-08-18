"""HelperSquadClient — moduł garbarnia.

Lekki kanał REST do Helper App (Render) dla funkcji "skład + trener" —
osobny od `core/managers/helper_relay_client.py` (WSS, dziś wyłączony,
zarezerwowany dla przyszłego strumienia zdarzeń live).

Moduł główny zawsze dzwoni wychodząco (POST push kadry, GET pull
propozycji) — Render nigdy nie łączy się do modułu głównego, bo ten jest
za NAT-em i nie ma jak przyjąć połączenia przychodzącego.
"""
import logging
from datetime import datetime

import requests
from flask import current_app

logger = logging.getLogger(__name__)

# (connect_timeout, read_timeout) — wysoki read timeout ze względu na cold
# start Render Hobby (apka może "spać" i wybudzać się kilkadziesiąt sekund).
_REQUEST_TIMEOUT = (5, 30)


def _base_url():
    return current_app.config['HELPER_APP_BASE_URL'].rstrip('/')


def _headers():
    return {'Authorization': f"Bearer {current_app.config['HELPER_APP_REST_TOKEN']}"}


class HelperSquadClient:

    def push_squad(self, game_id: int, team_id: int):
        """Wysyła pełną kadrę drużyny (+ trenera) do Helper App.

        Zwraca (ok: bool, message: str) — nigdy nie rzuca wyjątku transportowego,
        żeby awaria/cold-start Render nie wysypała requestu operatora.
        """
        from app.models.game import Game
        from app.models.team import Team
        from app.models.player import Player
        from app.models.game_player import GamePlayer

        game = Game.query.get(game_id)
        team = Team.query.get(team_id)
        if not game or not team:
            return False, 'Nie znaleziono meczu lub drużyny.'

        current_roles = {
            gp.player_id: gp.role
            for gp in GamePlayer.query.filter_by(game_id=game_id, team_id=team_id).all()
        }

        players_payload = []
        for player in Player.query.filter_by(team_id=team_id).all():
            players_payload.append({
                'player_id':     player.id,
                'first_name':    player.first_name,
                'last_name':     player.last_name,
                'number':        player.number,
                'is_goalkeeper': player.is_goalkeeper,
                'role':          current_roles.get(player.id, 'none'),
            })

        payload = {
            'game_id':    game_id,
            'team_id':    team_id,
            'team_label': team.name,
            'coach_name': team.coach,
            'players':    players_payload,
        }

        try:
            resp = requests.post(
                f'{_base_url()}/api/relay/squad',
                json=payload, headers=_headers(), timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.error('push_squad: Helper App odpowiedział %s: %s',
                             resp.status_code, resp.text[:300])
                return False, f'Helper App odrzucił żądanie ({resp.status_code}).'
            return True, f'Wysłano kadrę drużyny {team.name} do pomocnika.'
        except requests.exceptions.RequestException as e:
            logger.error('push_squad: błąd połączenia z Helper App: %s', e)
            return False, f'Brak połączenia z Helper App: {e}'

    def fetch_proposals(self):
        """Pobiera zgłoszone (status='submitted') propozycje z Helper App,
        zapisuje jako `HelperSquadProposal` (idempotentnie, po
        remote_squad_push_id). Zwraca (ok: bool, message: str, new_count: int).
        """
        from core.extensions import db
        from app.models.helper import Helper
        from app.models.helper_squad_proposal import HelperSquadProposal, STATUS_PENDING

        try:
            resp = requests.get(
                f'{_base_url()}/api/relay/squad/proposals',
                headers=_headers(), timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.error('fetch_proposals: Helper App odpowiedział %s: %s',
                             resp.status_code, resp.text[:300])
                return False, f'Helper App odrzucił żądanie ({resp.status_code}).', 0
            remote_proposals = resp.json().get('proposals', [])
        except requests.exceptions.RequestException as e:
            logger.error('fetch_proposals: błąd połączenia z Helper App: %s', e)
            return False, f'Brak połączenia z Helper App: {e}', 0
        except ValueError as e:
            logger.error('fetch_proposals: nieprawidłowa odpowiedź JSON: %s', e)
            return False, 'Helper App zwrócił nieprawidłową odpowiedź.', 0

        new_count = 0
        for item in remote_proposals:
            # Idempotentnie — Helper App może zwrócić ten sam rekord ponownie
            # w oknie retry (patrz relay.py po stronie Helper App).
            existing = HelperSquadProposal.query.filter_by(
                remote_squad_push_id=item['id']
            ).first()
            if existing:
                continue

            helper = None
            if item.get('helper_external_id'):
                helper = Helper.get_or_create(
                    item['helper_external_id'], item.get('helper_display_name')
                )

            submitted_at = None
            if item.get('submitted_at'):
                submitted_at = datetime.fromisoformat(item['submitted_at'])

            proposal = HelperSquadProposal(
                game_id=item['game_id'],
                team_id=item['team_id'],
                helper_id=helper.id if helper else None,
                remote_squad_push_id=item['id'],
                coach_name=item.get('coach_name'),
                status=STATUS_PENDING,
                submitted_at=submitted_at,
            )
            proposal.players = item.get('players', [])
            db.session.add(proposal)
            new_count += 1

        db.session.commit()
        return True, f'Pobrano {new_count} nowych propozycji.', new_count
