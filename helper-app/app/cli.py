import click

from .extensions import db
from .models import User


def register(app):
    @app.cli.command('create-admin')
    @click.option('--username', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(username, password):
        """Tworzy konto admina — `flask create-admin` (lokalnie, interaktywnie)."""
        if User.query.filter_by(username=username).first():
            click.echo(f'Użytkownik "{username}" już istnieje.')
            return

        admin = User(username=username, display_name='Administrator', role=User.ROLE_ADMIN)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f'Utworzono admina "{username}".')
