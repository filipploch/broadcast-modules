"""
core.models.settings — abstrakcyjna klasa Settings.

NIE importuj tej klasy bezpośrednio w kodzie core.
Zamiast tego użyj helpera get_settings_model() który zwraca
konkretną klasę zarejestrowaną przez aktywny moduł.

Dlaczego:
    core nie może definiować konkretnej tabeli 'settings' bo każdy moduł
    definiuje własną klasę Settings dziedziczącą z BaseSettings.
    Dwa __tablename__ = 'settings' w tej samej MetaData to błąd SQLAlchemy.
"""
from core.models.base_settings import BaseSettings


def get_settings_model():
    """
    Zwraca konkretną klasę Settings zarejestrowaną przez aktywny moduł.

    Używaj tej funkcji w kodzie core zamiast bezpośredniego importu:

        # ŹLE (w core):
        from core.models.settings import Settings
        settings = Settings.get_settings()

        # DOBRZE (w core):
        from core.models.settings import get_settings_model
        Settings = get_settings_model()
        settings = Settings.get_settings()
    """
    from core.extensions import db
    # Szukaj w mapperach SQLAlchemy klasy z __tablename__ == 'settings'
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'settings'
                and issubclass(cls, BaseSettings)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Settings w rejestrze SQLAlchemy. "
        "Upewnij się że app.models.settings.Settings jest zaimportowane "
        "przed pierwszym wywołaniem get_settings_model()."
    )


# Alias dla wstecznej kompatybilności — używaj tylko w module, nie w core
# W plikach core zawsze używaj get_settings_model()
Settings = None  # celowo None — wymusza użycie get_settings_model()
