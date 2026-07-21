"""BaseHelperMixin — tożsamość "pomocnika realizatora" (zewnętrzna apka na
Render, patrz docs/helper-app-design.md). Prosty pseudonim, bez hasła po
stronie modułu głównego — autentykacja pomocnik->Render to sprawa samej
apki.
"""
from core.extensions import db
from datetime import datetime


class BaseHelperMixin:

    id = db.Column(db.Integer, primary_key=True)
    external_id  = db.Column(db.String(100), nullable=False, unique=True, index=True)
    display_name = db.Column(db.String(200), nullable=True)
    is_active    = db.Column(db.Boolean, default=True, nullable=False)

    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<Helper {self.external_id!r}>'

    def to_dict(self):
        return {
            'id':            self.id,
            'external_id':   self.external_id,
            'display_name':  self.display_name,
            'is_active':     self.is_active,
            'last_seen_at':  self.last_seen_at.isoformat() if self.last_seen_at else None,
        }

    @classmethod
    def get_or_create(cls, external_id, display_name=None):
        helper = cls.query.filter_by(external_id=external_id).first()
        if helper is None:
            helper = cls(external_id=external_id, display_name=display_name)
            db.session.add(helper)
        helper.last_seen_at = datetime.utcnow()
        if display_name and not helper.display_name:
            helper.display_name = display_name
        db.session.commit()
        return helper


def get_helper_model():
    """Zwraca konkretną klasę BaseHelperMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'helpers'
                and issubclass(cls, BaseHelperMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseHelperMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_helper_model()."
    )
