"""Layout model - overlay stylingClass motywy (jeden rekord per dostępny
motyw tego modułu)."""
from core.extensions import db
from datetime import datetime


class BaseLayoutMixin:
    """Motyw ("layout") wyglądu overlayu tego modułu — co najwyżej jeden
    rekord ma is_active=True naraz (wymuszane przez LayoutManager.select,
    nie przez schemat bazy)."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Layout id={self.id} name={self.name!r} is_active={self.is_active}>'

    def to_dict(self):
        return {
            'id':        self.id,
            'name':      self.name,
            'is_active': self.is_active,
        }


def get_layout_model():
    """Zwraca klasę Layout zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'layouts'
                and issubclass(cls, BaseLayoutMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Layout w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
