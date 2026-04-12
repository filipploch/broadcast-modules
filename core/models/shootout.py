"""
core.models.shootout — abstrakcyjna klasa BaseShootout + helper get_shootout_model().

NIE importuj Shootout z tego pliku w kodzie core.
Używaj get_shootout_model() aby pobrać konkretną klasę zarejestrowaną przez moduł.
"""
from core.models.base_shootout import BaseShootout


def get_shootout_model():
    """Zwraca konkretną klasę Shootout zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'shootouts'
                and issubclass(cls, BaseShootout)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Shootout w rejestrze SQLAlchemy. "
        "Upewnij się że app.models.shootout.Shootout jest zaimportowane "
        "przed pierwszym wywołaniem get_shootout_model()."
    )