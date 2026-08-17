from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User

auth_bp = Blueprint('auth', __name__)


def _home_for(user: User) -> str:
    return url_for('admin.dashboard') if user.is_admin else url_for('helper.panel')


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and user.is_active and user.check_password(password):
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            login_user(user)
            return redirect(_home_for(user))

        flash('Nieprawidłowy login lub hasło.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
