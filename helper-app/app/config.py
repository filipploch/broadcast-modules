import os


def _normalize_db_url(url: str) -> str:
    """Render dostarcza DATABASE_URL z prefiksem postgres://, którego nowsze
    SQLAlchemy/psycopg nie akceptują — trzeba zamienić na postgresql://."""
    if url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get('DATABASE_URL', 'sqlite:///helper_app.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Token dla lekkiego kanału REST wywoływanego wychodząco przez moduł
    # główny (POST push kadry, GET pull propozycji) — osobny od
    # HELPER_RELAY_TOKEN, zarezerwowanego po stronie modułu głównego dla
    # przyszłego WSS relay.
    REST_TOKEN = os.environ.get('HELPER_APP_REST_TOKEN', '')
