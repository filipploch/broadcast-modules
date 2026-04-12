"""
core.models.shootout_kick — abstrakcyjna klasa BaseShootoutKick + helper get_shootout_kick_model().

NIE importuj ShootoutKick z tego pliku w kodzie core.
Używaj get_shootout_kick_model() aby pobrać konkretną klasę zarejestrowaną przez moduł.
"""
from core.models.base_shootout_kick import BaseShootoutKick


def get_shootout_kick_model():
    """Zwraca konkretną klasę ShootoutKick zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'shootout_kicks'
                and issubclass(cls, BaseShootoutKick)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy ShootoutKick w rejestrze SQLAlchemy. "
        "Upewnij się że app.models.shootout_kick.ShootoutKick jest zaimportowane "
        "przed pierwszym wywołaniem get_shootout_kick_model()."
    )