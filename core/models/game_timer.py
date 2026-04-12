"""
core.models.game_timer — abstrakcyjna klasa BaseGameTimer + helper.

NIE importuj GameTimer z tego pliku w kodzie core.
Używaj get_game_timer_model() aby pobrać konkretną klasę zarejestrowaną przez moduł.
"""
from core.models.base_game_timer import BaseGameTimer


def get_game_timer_model():
    """Zwraca konkretną klasę GameTimer zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_timers'
                and issubclass(cls, BaseGameTimer)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy GameTimer w rejestrze SQLAlchemy. "
        "Upewnij się że app.models.game_timer.GameTimer jest zaimportowane "
        "przed pierwszym wywołaniem get_game_timer_model()."
    )
