"""BackgroundImage model - Background images for OBS STREAM scene"""
from core.extensions import db
from datetime import datetime


class BaseBackgroundImageMixin:
    """Background image displayed in OBS STREAM scene via BackgroundImage source"""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=0)
    is_visible = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    path = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<BackgroundImage id={self.id} name={self.name!r}>'

    def to_dict(self):
        return {
            'id':          self.id,
            'name':        self.name,
            'order':       self.order,
            'is_visible':  self.is_visible,
            'path':        self.path,
            'static_url':  f'/static/{self.path}' if self.path else None,
            'description': self.description,
            'is_active':   self.is_active,
            'created_at':  self.created_at.isoformat() if self.created_at else None,
            'updated_at':  self.updated_at.isoformat() if self.updated_at else None,
        }


def get_background_image_model():
    """Zwraca klasę BackgroundImage zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'background_images'
                and issubclass(cls, BaseBackgroundImageMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BackgroundImage w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
