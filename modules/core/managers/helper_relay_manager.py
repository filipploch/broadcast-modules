"""HelperRelayManager — logika biznesowa dla zgłoszeń od pomocników:
deduplikacja, auto-odrzucanie duplikatów już zalogowanych zdarzeń,
zatwierdzanie/odrzucanie kandydatów, wypychanie stanu do apki na Render.

Patrz docs/helper-app-design.md (pełny opis reguł, sekcje 4-6).
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_helper():
    from core.models.base_helper import get_helper_model
    return get_helper_model()


def _get_candidate():
    from core.models.base_helper_event_candidate import get_helper_event_candidate_model
    return get_helper_event_candidate_model()


def _get_submission():
    from core.models.base_helper_event_submission import get_helper_event_submission_model
    return get_helper_event_submission_model()


def _get_game_event():
    from core.models.base_game_event import get_game_event_model
    return get_game_event_model()


def _get_period():
    from core.models.base_period import get_period_model
    return get_period_model()


def _default_tolerance_s():
    try:
        from flask import current_app
        return current_app.config.get('HELPER_MATCH_TOLERANCE_S', 8)
    except Exception:
        return 8


class HelperRelayManager:

    def __init__(self, relay_client=None):
        self.relay_client = relay_client

    # ------------------------------------------------------------------
    # Przyjmowanie zgłoszeń (od HelperRelayClient / testów)
    # ------------------------------------------------------------------

    def handle_incoming_submission(self, payload: dict):
        """
        payload:
          external_id (str, wymagane), display_name (opc.)
          game_id, period_id, event_time_delta_s (wymagane)
          event_id, team_id, player_id, comment (opc.)
          source_game_event_id (opc.) — obecność = korekta (kind='correction')
        """
        from core.extensions import db

        Helper = _get_helper()
        Candidate = _get_candidate()
        Submission = _get_submission()

        helper = Helper.get_or_create(payload['external_id'], payload.get('display_name'))

        game_id     = payload['game_id']
        period_id   = payload['period_id']
        event_time_delta_s = payload['event_time_delta_s']
        event_id    = payload.get('event_id')
        team_id     = payload.get('team_id')
        player_id   = payload.get('player_id')
        comment     = payload.get('comment')
        source_game_event_id = payload.get('source_game_event_id')
        kind = Candidate.KIND_CORRECTION if source_game_event_id else Candidate.KIND_NEW
        tolerance_s = _default_tolerance_s()

        auto_reject_reason = self._check_auto_reject(
            kind, game_id, period_id, event_time_delta_s, event_id, team_id,
            player_id, source_game_event_id, tolerance_s,
        )

        candidate = None
        if auto_reject_reason is None:
            candidate = Candidate.find_matching_pending(
                game_id, period_id, kind, event_time_delta_s=event_time_delta_s,
                event_id=event_id, team_id=team_id,
                source_game_event_id=source_game_event_id, tolerance_s=tolerance_s,
            )

        if candidate is None:
            candidate = Candidate(
                game_id=game_id, period_id=period_id, kind=kind,
                event_id=event_id, team_id=team_id, player_id=player_id,
                event_time_delta_s=event_time_delta_s, comment=comment,
                source_game_event_id=source_game_event_id,
                status=Candidate.STATUS_AUTO_REJECTED if auto_reject_reason else Candidate.STATUS_PENDING,
                status_reason=auto_reject_reason,
            )
            db.session.add(candidate)
            db.session.flush()
        elif kind == Candidate.KIND_CORRECTION:
            # Korekta może ewoluować — kolejne zgłoszenie tej samej korekty
            # niesie najnowszą propozycję wartości.
            candidate.event_id = event_id
            candidate.team_id = team_id
            candidate.player_id = player_id
            candidate.comment = comment
            candidate.updated_at = datetime.utcnow()

        submission = Submission(
            helper_id=helper.id, candidate_id=candidate.id,
            game_id=game_id, period_id=period_id, event_time_delta_s=event_time_delta_s,
            event_id=event_id, team_id=team_id, player_id=player_id,
            comment=comment, source_game_event_id=source_game_event_id,
        )
        db.session.add(submission)
        db.session.commit()

        logger.info(
            f"[helper-relay] submission from '{helper.external_id}' -> "
            f"candidate {candidate.id} (status={candidate.status})"
        )

        if candidate.status == Candidate.STATUS_PENDING:
            self._emit_to_ui('helper_candidate_updated', candidate.to_dict())

        return candidate

    def _check_auto_reject(self, kind, game_id, period_id, event_time_delta_s, event_id,
                            team_id, player_id, source_game_event_id, tolerance_s):
        """Zwraca status_reason (str) jeśli zgłoszenie duplikuje coś już
        zalogowanego w GameEvent, albo None jeśli nie ma podstaw do
        auto-odrzucenia. Patrz docs/helper-app-design.md sekcja 4-5."""
        GameEvent = _get_game_event()
        Candidate = _get_candidate()

        if kind == Candidate.KIND_CORRECTION:
            source = GameEvent.query.get(source_game_event_id)
            if source is None:
                return "source_game_event_not_found"
            if source.event_id == event_id and source.team_id == team_id and source.player_id == player_id:
                return "correction_matches_current_state"
            return None

        Period = _get_period()
        period = Period.query.get(period_id)
        if not period:
            return None
        target_game_time = period.initial_time // 1000 + event_time_delta_s

        existing = GameEvent.query.filter_by(
            game_id=game_id, period_id=period_id, event_id=event_id, team_id=team_id,
        ).all()
        for ge in existing:
            if ge.game_time is not None and abs(int(ge.game_time) - target_game_time) <= tolerance_s:
                return f"duplicate_of_game_event:{ge.id}"
        return None

    # ------------------------------------------------------------------
    # Decyzje operatora
    # ------------------------------------------------------------------

    def get_pending_candidates(self, league_id):
        return _get_candidate().get_pending_for_league(league_id)

    def get_candidates_for_game(self, game_id, status=None):
        return _get_candidate().get_for_game(game_id, status=status)

    def approve_candidate(self, candidate_id):
        from core.extensions import db
        from core.managers.game_event_manager import GameEventManager

        Candidate = _get_candidate()
        candidate = Candidate.query.get(candidate_id)
        if not candidate:
            raise ValueError(f"Kandydat o ID {candidate_id} nie istnieje")
        if candidate.status != Candidate.STATUS_PENDING:
            raise ValueError(f"Kandydat {candidate_id} nie oczekuje na decyzję (status={candidate.status})")

        gem = GameEventManager()

        if candidate.kind == Candidate.KIND_NEW:
            game_event = gem.record_event_at_time(
                game_id=candidate.game_id, period_id=candidate.period_id,
                event_time_delta_s=candidate.event_time_delta_s, event_id=candidate.event_id,
                team_id=candidate.team_id, player_id=candidate.player_id,
                comment=candidate.comment,
            )
        else:
            game_event = gem.update_game_event(
                candidate.source_game_event_id, event_id=candidate.event_id,
                team_id=candidate.team_id, player_id=candidate.player_id,
                comment=candidate.comment,
            )

        candidate.status = Candidate.STATUS_APPROVED
        candidate.resolved_game_event_id = game_event.id
        candidate.resolved_at = datetime.utcnow()
        db.session.commit()

        # Uwaga: GameEventManager.record_event_at_time()/update_game_event()
        # już same wypychają notify_event_recorded() do relaya — nie robimy
        # tego drugi raz tutaj.
        logger.info(f"[helper-relay] candidate {candidate_id} approved -> game_event {game_event.id}")
        return candidate

    def reject_candidate(self, candidate_id, reason=None):
        """Miękkie odrzucenie — wiersz zostaje w bazie, tylko znika z listy
        'do przejrzenia' (patrz docs/helper-app-design.md sekcja 4)."""
        from core.extensions import db

        Candidate = _get_candidate()
        candidate = Candidate.query.get(candidate_id)
        if not candidate:
            raise ValueError(f"Kandydat o ID {candidate_id} nie istnieje")
        if candidate.status != Candidate.STATUS_PENDING:
            raise ValueError(f"Kandydat {candidate_id} nie oczekuje na decyzję (status={candidate.status})")

        candidate.status = Candidate.STATUS_REJECTED
        candidate.status_reason = reason
        candidate.resolved_at = datetime.utcnow()
        db.session.commit()
        logger.info(f"[helper-relay] candidate {candidate_id} rejected ({reason})")
        return candidate

    # ------------------------------------------------------------------
    # Wypychanie stanu do apki (best-effort — no-op jeśli relay wyłączony
    # albo niepołączony, patrz docs/helper-app-design.md sekcja 6)
    # ------------------------------------------------------------------

    def notify_period_state(self, period, state: str):
        """state: 'started' | 'finished'"""
        if not self.relay_client:
            return
        self.relay_client.push('period_state', {
            'period_id': period.id,
            'game_id': period.game_id,
            'period_order': period.period_order,
            'state': state,
        })

    def notify_event_recorded(self, game_event):
        if not self.relay_client:
            return
        self.relay_client.push('event_recorded', {
            'game_event_id': game_event.id,
            'game_id': game_event.game_id,
            'period_id': game_event.period_id,
            'event_id': game_event.event_id,
            'team_id': game_event.team_id,
            'player_id': game_event.player_id,
            'game_time': int(game_event.game_time) if game_event.game_time is not None else None,
        })

    def _emit_to_ui(self, msg_type, data):
        try:
            from core.extensions import socketio
            socketio.emit(msg_type, data)
        except Exception as e:
            logger.error(f"[helper-relay] Failed to emit to UI: {e}")
