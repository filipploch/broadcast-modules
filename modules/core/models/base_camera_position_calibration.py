"""CameraPositionCalibration — kalibracja pan/tilt dla pary (pozycja, strefa)."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseCameraPositionCalibrationMixin:
    """
    Wartości pan i tilt dla głowicy stojącej w konkretnym miejscu (position_id),
    skierowanej w konkretną strefę (zone_code).

    Kalibracja jest jednorazowa per obiekt — te same wartości są używane
    dla każdego zdarzenia (meczu, wyścigu) na danym obiekcie.

    Schemat stref zależy od zone_scheme obiektu:
      FIELD_GRID   — siatka A1–O9 (boisko futsalu / piłki nożnej)
      TRACK_LINEAR — dowolne kody stref liniowych, np. "G01"–"G30" (narty, karting, rafting)
    """

    id          = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(
        db.Integer,
        db.ForeignKey('stadium_camera_positions.id'),
        nullable=False,
        index=True,
    )
    # Kamera której dotyczy kalibracja — różne montaże dają różne kąty dla tej samej strefy.
    # NULL = kalibracja generyczna (dane legacy bez przypisanej kamery).
    camera_id   = db.Column(db.Integer, db.ForeignKey('cameras.id'), nullable=True, index=True)
    # Identyfikator strefy: "A1"–"O9" dla FIELD_GRID, dowolny String dla TRACK_LINEAR
    zone_code   = db.Column(db.String(30), nullable=False)
    pan         = db.Column(db.Integer, nullable=False)   # 0–180
    tilt        = db.Column(db.Integer, nullable=False)   # 0–180

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def camera(cls):
        return db.relationship('Camera', foreign_keys='[CameraPositionCalibration.camera_id]')

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('position_id', 'camera_id', 'zone_code',
                                name='uix_calibration_position_camera_zone'),
            db.CheckConstraint('pan  >= 0 AND pan  <= 180', name='check_calibration_pan_range'),
            db.CheckConstraint('tilt >= 0 AND tilt <= 180', name='check_calibration_tilt_range'),
        )

    def __repr__(self):
        return (
            f'<CameraPositionCalibration position_id={self.position_id} '
            f'zone={self.zone_code} pan={self.pan} tilt={self.tilt}>'
        )

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'position_id': self.position_id,
            'camera_id':   self.camera_id,
            'zone_code':   self.zone_code,
            'pan':         self.pan,
            'tilt':        self.tilt,
        }


def get_camera_position_calibration_model():
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'camera_position_calibrations'
                and issubclass(cls, BaseCameraPositionCalibrationMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy CameraPositionCalibration w rejestrze SQLAlchemy."
    )
