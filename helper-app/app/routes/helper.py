from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import SquadPush, SquadPushPlayer

helper_bp = Blueprint('helper', __name__)

# TODO: to na razie statyczny szkic UI. Docelowo typy zdarzeń, drużyny i
# timeline już zalogowanych zdarzeń mają przychodzić live przez połączenie
# HelperRelay z modułu głównego (docs/helper-app-design.md, sekcja 6) —
# nie są jeszcze tutaj podłączone.
MOCK_EVENT_TYPES = [
    {'id': 'goal', 'label': '⚽ Bramka'},
    {'id': 'foul', 'label': '🟨 Faul'},
    {'id': 'miss', 'label': '❌ Pudło'},
    {'id': 'save', 'label': '🧤 Obrona'},
]

MOCK_TEAMS = [
    {'id': 'home', 'label': 'Gospodarze'},
    {'id': 'away', 'label': 'Goście'},
]


@helper_bp.route('/panel')
@login_required
def panel():
    return render_template(
        'helper/panel.html',
        event_types=MOCK_EVENT_TYPES,
        teams=MOCK_TEAMS,
    )


@helper_bp.route('/panel/submit', methods=['POST'])
@login_required
def submit_event():
    # TODO: brak jeszcze połączenia z modułem głównym (HelperRelay) —
    # to tylko szkic UI, zgłoszenie nigdzie faktycznie nie trafia.
    flash(
        'Szkic UI: zgłoszenie nie zostało wysłane — brak jeszcze połączenia '
        'z modułem głównym.',
        'info',
    )
    return redirect(url_for('helper.panel'))


# ============================================================================
# SKŁAD MECZOWY (wyjściowa jedenastka / rezerwa / trener) — pierwsza realna
# funkcja, patrz helper-app/README.md i docs/helper-app-design.md (moduł
# główny) dla kontekstu kanału REST.
# ============================================================================

@helper_bp.route('/panel/squad')
@login_required
def squad_list():
    pushes = (SquadPush.query
              .filter_by(status=SquadPush.STATUS_OPEN)
              .order_by(SquadPush.received_at.desc())
              .all())
    return render_template('helper/squad_list.html', pushes=pushes)


@helper_bp.route('/panel/squad/<int:squad_push_id>')
@login_required
def squad_assign(squad_push_id):
    squad_push = SquadPush.query.get_or_404(squad_push_id)
    return render_template('helper/squad_assign.html', squad_push=squad_push)


@helper_bp.route('/panel/squad/<int:squad_push_id>/save', methods=['POST'])
@login_required
def squad_save(squad_push_id):
    squad_push = SquadPush.query.get_or_404(squad_push_id)
    if squad_push.status != SquadPush.STATUS_OPEN:
        flash('Ta propozycja została już wysłana — nie można jej edytować.', 'error')
        return redirect(url_for('helper.squad_assign', squad_push_id=squad_push_id))

    for sp_player in squad_push.players:
        role = request.form.get(f'role_{sp_player.id}', SquadPushPlayer.ROLE_NONE)
        if role in SquadPushPlayer.ROLES:
            sp_player.role = role

    new_coach = request.form.get('coach_name', '').strip()
    if new_coach != (squad_push.coach_name or ''):
        squad_push.coach_name = new_coach or None
        squad_push.coach_name_source = SquadPush.COACH_SOURCE_EDITED

    db.session.commit()
    flash('Zapisano zmiany.', 'success')
    return redirect(url_for('helper.squad_assign', squad_push_id=squad_push_id))


@helper_bp.route('/panel/squad/<int:squad_push_id>/submit', methods=['POST'])
@login_required
def squad_submit(squad_push_id):
    squad_push = SquadPush.query.get_or_404(squad_push_id)
    if squad_push.status != SquadPush.STATUS_OPEN:
        flash('Ta propozycja została już wysłana.', 'info')
        return redirect(url_for('helper.squad_assign', squad_push_id=squad_push_id))

    squad_push.status = SquadPush.STATUS_SUBMITTED
    squad_push.submitted_by_user_id = current_user.id
    squad_push.submitted_at = datetime.utcnow()
    db.session.commit()
    flash('Wysłano propozycję do modułu głównego.', 'success')
    return redirect(url_for('helper.squad_list'))
