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
