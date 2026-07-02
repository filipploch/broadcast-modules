"""Camera model - Camera equipment used in games"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseCameraMixin:
    """Camera equipment (physical camera device)"""

    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(50),  nullable=False)
    model = db.Column(db.String(100), nullable=False)

    # Zmotoryzowana głowica pan/tilt sparowana z tą kamerą (1:1, nullable)
    cam_head_id = db.Column(db.Integer, db.ForeignKey('cam_heads.id'), nullable=True)

    # Dane WiFi kamery GoPro (nullable — nie wszystkie kamery to GoPro)
    gopro_ssid     = db.Column(db.String(100), nullable=True)
    gopro_password = db.Column(db.String(100), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def is_motorized(self) -> bool:
        return self.cam_head_id is not None

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('cam_head_id', name='uix_camera_cam_head_id'),
        )

    @declared_attr
    def cam_head(cls):
        return db.relationship('CamHead', back_populates='camera', uselist=False)

    @declared_attr
    def game_cameras(cls):
        return db.relationship('GameCamera', backref='camera', lazy='dynamic', cascade='all, delete-orphan')

    @declared_attr
    def event_cameras(cls):
        return db.relationship('EventCamera', backref='camera', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Camera {self.name} ({self.brand} {self.model})>'

    def to_dict(self):
        return {
            'id':             self.id,
            'name':           self.name,
            'brand':          self.brand,
            'model':          self.model,
            'cam_head_id':    self.cam_head_id,
            'is_motorized':   self.is_motorized,
            'gopro_ssid':     self.gopro_ssid,
            'created_at':     self.created_at.isoformat() if self.created_at else None,
            'updated_at':     self.updated_at.isoformat() if self.updated_at else None,
        }

def get_camera_model():
    """Zwraca klasę Camera zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'cameras'
                and issubclass(cls, BaseCameraMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Camera w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
