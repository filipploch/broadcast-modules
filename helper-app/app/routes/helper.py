from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

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
