"""InterviewManager — lista uczestników wywiadu (zakładka "WYWIAD" w adminie)
i orkiestracja sygnałów hub sterujących kartą na overlayu.

Adresowanie wiadomości do overlayu jest identyczne jak w
core.sequences.steps.show_overlay_container: `to: 'stream-overlay'` (direct),
NIE broadcast:<class> — tak jest zaadresowana cała istniejąca ścieżka
overlayu w tym repo (patrz plugin "stream-overlay" rejestrujący się w hubie
jako strona overlay.html).
"""
from core.extensions import db


def _get_interview_participant():
    from core.models.base_interview_participant import get_interview_participant_model
    return get_interview_participant_model()


def _get_player():
    from core.models.base_player import get_player_model
    return get_player_model()


def _get_referee():
    from core.models.base_referee import get_referee_model
    return get_referee_model()


def _get_commentator():
    from core.models.base_commentator import get_commentator_model
    return get_commentator_model()


def _get_team():
    from core.models.base_team import get_team_model
    return get_team_model()


# Domyślne opisy per typ — patrz specyfikacja użytkownika.
DEFAULT_DESCRIPTIONS = {
    'redaktor': 'NALFvideo',
    'zawodnik': 'Zawodnik',
    'trener':   'Trener',
    'sedzia':   'Sędzia',
    'inne':     '',
}

# Domyślne obrazki per typ — pliki trzeba dołożyć w modules/static/images/interview/.
DEFAULT_IMAGES = {
    'redaktor': '/static/images/interview/redaktor.png',
    'zawodnik': '/static/images/interview/zawodnik.png',
    'trener':   '/static/images/interview/trener.png',
    'sedzia':   '/static/images/interview/sedzia.png',
    'inne':     '/static/images/interview/inne.png',
}

TYPE_LABELS = {
    'redaktor': 'Redaktor',
    'zawodnik': 'Zawodnik',
    'trener':   'Trener',
    'sedzia':   'Sędzia',
    'inne':     'Inne',
}


class InterviewManager:

    # ── Lista / CRUD ─────────────────────────────────────────────────────

    def list_for_game(self, game_id):
        InterviewParticipant = _get_interview_participant()
        rows = (InterviewParticipant.query
                .filter_by(game_id=game_id)
                .order_by(InterviewParticipant.created_at.asc())
                .all())
        return [r.to_dict() for r in rows]

    def add(self, game_id, interview_type, name, description, image_path,
            matched_player_id=None, matched_referee_id=None, matched_commentator_id=None,
            matched_team_id=None, use_team_crest=False):
        InterviewParticipant = _get_interview_participant()
        row = InterviewParticipant(
            game_id=game_id,
            interview_type=interview_type,
            name=name,
            description=description,
            image_path=image_path,
            matched_player_id=matched_player_id,
            matched_referee_id=matched_referee_id,
            matched_commentator_id=matched_commentator_id,
            matched_team_id=matched_team_id,
            use_team_crest=bool(use_team_crest),
        )
        db.session.add(row)
        db.session.commit()
        return row

    def remove(self, participant_id):
        InterviewParticipant = _get_interview_participant()
        row = InterviewParticipant.query.get(participant_id)
        if not row:
            return None
        was_active = row.is_active
        game_id = row.game_id
        db.session.delete(row)
        db.session.commit()
        if was_active:
            self._send_hub_message('hide_interview', {})
        return game_id

    def reset(self, game_id):
        InterviewParticipant = _get_interview_participant()
        rows = InterviewParticipant.query.filter_by(game_id=game_id).all()
        any_active = any(r.is_active for r in rows)
        for r in rows:
            db.session.delete(r)
        db.session.commit()
        if any_active:
            self._send_hub_message('hide_interview', {})

    # ── Wyszukiwanie podpowiedzi (autocomplete) ─────────────────────────

    def search_people(self, query, interview_type):
        query = (query or '').strip()
        if not query or interview_type not in ('redaktor', 'zawodnik', 'sedzia', 'trener'):
            return []

        if interview_type == 'redaktor':
            return self._search_commentators(query)
        if interview_type == 'zawodnik':
            return self._search_players(query)
        if interview_type == 'sedzia':
            return self._search_referees(query)
        if interview_type == 'trener':
            return self._search_coaches(query)
        return []

    def _matches(self, haystack, query):
        return query.lower() in (haystack or '').lower()

    def _search_players(self, query):
        Player = _get_player()
        players = Player.query.all()
        results = []
        for p in players:
            if self._matches(p.full_name, query):
                team = p.team if p.team_id else None
                results.append({
                    'label': p.full_name,
                    'name': p.full_name,
                    'matched_player_id': p.id,
                    'matched_team_id': p.team_id,
                    'team_short_name': team.short_name if team else None,
                    'team_name': team.name if team else None,
                    'team_name_14': team.name_14 if team else None,
                    'team_logo': team.logo_path if team else None,
                })
        return results[:20]

    def _search_commentators(self, query):
        Commentator = _get_commentator()
        commentators = Commentator.query.all()
        results = []
        for c in commentators:
            if self._matches(c.full_name, query):
                results.append({
                    'label': c.full_name,
                    'name': c.full_name,
                    'matched_commentator_id': c.id,
                    'matched_team_id': None,
                    'team_short_name': None,
                    'team_name': None,
                    'team_name_14': None,
                    'team_logo': None,
                })
        return results[:20]

    def _search_referees(self, query):
        Referee = _get_referee()
        referees = Referee.query.all()
        results = []
        for r in referees:
            if self._matches(r.full_name, query):
                results.append({
                    'label': r.full_name,
                    'name': r.full_name,
                    'matched_referee_id': r.id,
                    'matched_team_id': None,
                    'team_short_name': None,
                    'team_name': None,
                    'team_name_14': None,
                    'team_logo': None,
                })
        return results[:20]

    def _search_coaches(self, query):
        Team = _get_team()
        # Trener istnieje tylko jako Team.coach (garbarnia) — w modułach bez
        # tej kolumny (futsal_nalf) po prostu nie ma podpowiedzi, bez błędu.
        if not hasattr(Team, 'coach'):
            return []
        teams = Team.query.filter(Team.coach.isnot(None)).all()
        results = []
        for t in teams:
            if t.coach and self._matches(t.coach, query):
                results.append({
                    'label': t.coach,
                    'name': t.coach,
                    'matched_team_id': t.id,
                    'team_short_name': t.short_name,
                    'team_name': t.name,
                    'team_name_14': t.name_14,
                    'team_logo': t.logo_path,
                })
        return results[:20]

    # ── Toggle "W" ───────────────────────────────────────────────────────

    def toggle(self, participant_id):
        InterviewParticipant = _get_interview_participant()
        row = InterviewParticipant.query.get(participant_id)
        if not row:
            return None

        if row.is_active:
            self._send_hub_message('hide_interview', {})
            row.is_active = False
            db.session.commit()
            return row.game_id

        other_active = (InterviewParticipant.query
                        .filter_by(game_id=row.game_id, is_active=True)
                        .all())
        if other_active:
            self._send_hub_message('hide_interview', {})
            for other in other_active:
                other.is_active = False

        self._send_hub_message('update_interview', {
            'image': row.image_path,
            'name': row.name,
            'description': row.description,
        })
        self._send_hub_message('show_interview', {'participant_id': row.id})
        row.is_active = True
        db.session.commit()
        return row.game_id

    def deactivate(self, participant_id):
        """Gasi is_active bez wysyłania żadnego sygnału do huba — overlay już
        się sam ukrył (auto-hide), to tylko domknięcie stanu w DB/UI.
        Zwraca game_id (do odświeżenia listy) albo None."""
        InterviewParticipant = _get_interview_participant()
        row = InterviewParticipant.query.get(participant_id)
        if row and row.is_active:
            row.is_active = False
            db.session.commit()
            return row.game_id
        return None

    # ── Hub ──────────────────────────────────────────────────────────────

    def _send_hub_message(self, msg_type, payload):
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if not hub_client:
            return
        from flask import current_app
        hub_client.send({
            'from': current_app.config['MODULE_ID'],
            'to': 'stream-overlay',
            'type': msg_type,
            'payload': payload,
        })
