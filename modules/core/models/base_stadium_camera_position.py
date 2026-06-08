"""StadiumCameraPosition — predefiniowane miejsce montażu kamery GoPro na stadionie."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseStadiumCameraPositionMixin:
    """
    Fizyczne miejsce, w którym można zamontować głowicę pan/tilt z kamerą GoPro.

    Każdy stadion ma własny zestaw pozycji (np. "Narożnik NE", "Za bramką Południe").
    Do każdej pozycji przypisana jest kalibracja pan/tilt dla komórek boiska A1–O9
    (tabela camera_position_calibrations).

    Podczas planowania transmisji operator wskazuje, które pozycje są obsadzone
    i którym urządzeniem cam-head (tabela game_gopro_setups).
    """

    id         = db.Column(db.Integer, primary_key=True)
    stadium_id = db.Column(db.Integer, db.ForeignKey('stadiums.id'), nullable=False, index=True)
    name       = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sort_order  = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def calibrations(cls):
        return db.relationship(
            'CameraPositionCalibration',
            backref='position',
            lazy='dynamic',
            cascade='all, delete-orphan',
        )

    @declared_attr
    def game_setups(cls):
        return db.relationship(
            'GameGoProSetup',
            backref='position',
            lazy='dynamic',
            cascade='all, delete-orphan',
        )

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('stadium_id', 'name', name='uix_stadium_camera_position'),
        )

    def get_aim(self, cell_code: str) -> tuple[int, int] | None:
        """Zwraca (pan, tilt) dla podanej komórki boiska, lub None jeśli brak kalibracji."""
        cal = self.calibrations.filter_by(cell_code=cell_code).first()
        return (cal.pan, cal.tilt) if cal else None

    def __repr__(self):
        return f'<StadiumCameraPosition stadium_id={self.stadium_id} name="{self.name}">'

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'stadium_id':  self.stadium_id,
            'name':        self.name,
            'description': self.description,
            'sort_order':  self.sort_order,
        }


def get_stadium_camera_position_model():
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'stadium_camera_positions'
                and issubclass(cls, BaseStadiumCameraPositionMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy StadiumCameraPosition w rejestrze SQLAlchemy."
    )
