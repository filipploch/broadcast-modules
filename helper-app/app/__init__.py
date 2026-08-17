import os

from flask import Flask

from .config import Config
from .extensions import db, login_manager
from .models import User


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Zaloguj się, aby kontynuować.'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .routes.admin import admin_bp
    from .routes.auth import auth_bp
    from .routes.helper import helper_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(helper_bp)

    with app.app_context():
        db.create_all()
        _bootstrap_admin_from_env()

    from . import cli
    cli.register(app)

    return app


def _bootstrap_admin_from_env():
    """Przy pierwszym starcie (brak jeszcze żadnego admina) tworzy konto
    admina z ADMIN_USERNAME/ADMIN_PASSWORD, jeśli te zmienne są ustawione.

    Wygodne na Render Hobby, gdzie nie ma łatwego dostępu do powłoki, żeby
    odpalić `flask create-admin` interaktywnie.
    """
    if User.query.filter_by(role=User.ROLE_ADMIN).first():
        return

    username = os.environ.get('ADMIN_USERNAME')
    password = os.environ.get('ADMIN_PASSWORD')
    if not username or not password:
        return

    admin = User(username=username, display_name='Administrator', role=User.ROLE_ADMIN)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
