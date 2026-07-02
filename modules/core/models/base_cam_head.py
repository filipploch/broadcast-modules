"""CamHead — zmotoryzowana głowica pan/tilt (ESP32)."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseCamHeadMixin:
    """
    Fizyczna głowica pan/tilt sterowana przez ESP32.

    head_id to identyfikator nadawany przez firmware ESP32 (unikalny w obrębie modułu).
    ServoManager używa head_id jako klucza do śledzenia stanu online/offline.
    Relacja z Camera jest 1:1 — głowica jest zawsze sparowana z jedną kamerą.
    """

    id         = db.Column(db.Integer, primary_key=True)
    head_id    = db.Column(db.String(50), nullable=False, unique=True)
    name       = db.Column(db.String(100), nullable=True)
    last_seen  = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def camera(cls):
        return db.relationship('Camera', back_populates='cam_head', uselist=False)

    def __repr__(self):
        return f'<CamHead head_id={self.head_id!r} name={self.name!r}>'

    def to_dict(self) -> dict:
        return {
            'id':        self.id,
            'head_id':   self.head_id,
            'name':      self.name,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
        }


def get_cam_head_model():
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'cam_heads'
                and issubclass(cls, BaseCamHeadMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy CamHead w rejestrze SQLAlchemy."
    )
