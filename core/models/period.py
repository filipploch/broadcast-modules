"""
core.models.period — abstrakcyjna klasa BasePeriod + helper get_period_model().

NIE importuj Period z tego pliku w kodzie core.
Używaj get_period_model() aby pobrać konkretną klasę zarejestrowaną przez moduł.
"""
from core.models.base_period import BasePeriod


def get_period_model():
    """Zwraca konkretną klasę Period zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'periods'
                and issubclass(cls, BasePeriod)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Period w rejestrze SQLAlchemy. "
        "Upewnij się że app.models.period.Period jest zaimportowane "
        "przed pierwszym wywołaniem get_period_model()."
    )
