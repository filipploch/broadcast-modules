"""Banner model - Banners displayed on stream overlay"""
from core.extensions import db
from datetime import datetime


class BaseBannerMixin:
    """Banner displayed on stream overlay"""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    source = db.Column(db.Text, nullable=False)
    order = db.Column(db.Integer, nullable=False, default=0)
    is_visible = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    activation_function = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Banner id={self.id} name={self.name!r}>'

    def to_dict(self):
        return {
            'id':                  self.id,
            'name':                self.name,
            'source':              self.source,
            'order':               self.order,
            'is_visible':          self.is_visible,
            'activation_function': self.activation_function,
            'created_at':          self.created_at.isoformat() if self.created_at else None,
            'updated_at':          self.updated_at.isoformat() if self.updated_at else None,
        }


def get_banner_model():
    """Zwraca klasę Banner zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'banners'
                and issubclass(cls, BaseBannerMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Banner w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
