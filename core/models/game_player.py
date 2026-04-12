"""
core.models.game_player — abstrakcyjna klasa BaseGamePlayer + helper.

NIE importuj GamePlayer z tego pliku w kodzie core.
Używaj get_game_player_model() aby pobrać konkretną klasę zarejestrowaną przez moduł.
"""
from core.models.base_game_player import BaseGamePlayer


def get_game_player_model():
    """Zwraca konkretną klasę GamePlayer zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_players'
                and issubclass(cls, BaseGamePlayer)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy GamePlayer w rejestrze SQLAlchemy. "
        "Upewnij się że app.models.game_player.GamePlayer jest zaimportowane "
        "przed pierwszym wywołaniem get_game_player_model()."
    )
