import secrets
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import User

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash('Brak uprawnień.', 'error')
            return redirect(url_for('helper.panel'))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route('/')
@admin_required
def dashboard():
    helpers = (User.query
               .filter_by(role=User.ROLE_HELPER)
               .order_by(User.created_at.desc())
               .all())
    return render_template('admin/dashboard.html', helpers=helpers)


@admin_bp.route('/helpers/new', methods=['POST'])
@admin_required
def create_helper():
    username = request.form.get('username', '').strip()
    display_name = request.form.get('display_name', '').strip()

    if not username:
        flash('Login jest wymagany.', 'error')
        return redirect(url_for('admin.dashboard'))

    if User.query.filter_by(username=username).first():
        flash(f'Login "{username}" jest już zajęty.', 'error')
        return redirect(url_for('admin.dashboard'))

    # Hasło tymczasowe — pokazane raz w komunikacie, pomocnik powinien
    # dostać je bezpiecznym kanałem poza tą apką (nie ma tu jeszcze
    # "zmień hasło przy pierwszym logowaniu" — do dopracowania).
    temp_password = secrets.token_urlsafe(6)
    helper = User(
        username=username,
        display_name=display_name or username,
        role=User.ROLE_HELPER,
    )
    helper.set_password(temp_password)
    db.session.add(helper)
    db.session.commit()

    flash(f'Utworzono pomocnika "{username}". Tymczasowe hasło: {temp_password}', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/helpers/<int:helper_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_helper_active(helper_id):
    helper = User.query.filter_by(id=helper_id, role=User.ROLE_HELPER).first_or_404()
    helper.active = not helper.active
    db.session.commit()
    return redirect(url_for('admin.dashboard'))
