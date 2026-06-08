"""CameraPositionCalibration — kalibracja pan/tilt dla pary (pozycja, komórka boiska)."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseCameraPositionCalibrationMixin:
    """
    Wartości pan i tilt dla głowicy stojącej w konkretnym miejscu (position_id),
    skierowanej w konkretną komórkę boiska (cell_code A1–O9).

    Kalibracja jest jednorazowa per stadion — te same wartości są używane
    dla każdego meczu rozgrywanego na danym stadionie.

    Siatkę boiska tworzy 135 komórek: kolumny A–O (15) × wiersze 1–9 (9).
    """

    id          = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(
        db.Integer,
        db.ForeignKey('stadium_camera_positions.id'),
        nullable=False,
        index=True,
    )
    # Kod komórki boiska: "A1"–"O9"
    cell_code   = db.Column(db.String(3), nullable=False)
    pan         = db.Column(db.Integer, nullable=False)   # 0–180
    tilt        = db.Column(db.Integer, nullable=False)   # 0–90

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('position_id', 'cell_code', name='uix_calibration_position_cell'),
            db.CheckConstraint('pan  >= 0 AND pan  <= 180', name='check_calibration_pan_range'),
            db.CheckConstraint('tilt >= 0 AND tilt <= 90',  name='check_calibration_tilt_range'),
        )

    def __repr__(self):
        return (
            f'<CameraPositionCalibration position_id={self.position_id} '
            f'cell={self.cell_code} pan={self.pan} tilt={self.tilt}>'
        )

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'position_id': self.position_id,
            'cell_code':   self.cell_code,
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
