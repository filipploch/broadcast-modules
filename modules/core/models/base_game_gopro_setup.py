"""GameGoProSetup — przypisanie głowicy cam-head do pozycji na czas konkretnego meczu."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseGameGoProSetupMixin:
    """
    Planowanie obsady kamer GoPro na mecz.

    Operator wskazuje:
      - position_id  → które miejsce na stadionie jest obsadzone
      - cam_head_id  → identyfikator pluginu ESP32 ("cam-head-1", "cam-head-2"…)

    Na podstawie tej tabeli + camera_position_calibrations system wie,
    jakie wartości pan/tilt wysłać do konkretnego urządzenia ESP32
    gdy operator celuje w wybraną komórkę boiska.

    Ograniczenia unikalności (per mecz):
      - jedno urządzenie cam-head może obsadzić tylko jedną pozycję
      - na jednej pozycji może stać tylko jedno urządzenie
    """

    id          = db.Column(db.Integer, primary_key=True)
    game_id     = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    position_id = db.Column(
        db.Integer,
        db.ForeignKey('stadium_camera_positions.id'),
        nullable=False,
        index=True,
    )
    # Identyfikator pluginu ESP32, np. "cam-head-1"
    cam_head_id = db.Column(db.String(50), nullable=False)
    is_active   = db.Column(db.Boolean, nullable=False, default=True)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @declared_attr
    def __table_args__(cls):
        return (
            db.UniqueConstraint('game_id', 'position_id',  name='uix_gopro_setup_game_position'),
            db.UniqueConstraint('game_id', 'cam_head_id',  name='uix_gopro_setup_game_device'),
        )

    def get_aim(self, cell_code: str) -> tuple[int, int] | None:
        """
        Zwraca (pan, tilt) dla podanej komórki boiska na podstawie kalibracji pozycji.
        Shortcut do position.get_aim() — None jeśli pozycja lub kalibracja nie istnieje.
        """
        return self.position.get_aim(cell_code) if self.position else None

    def __repr__(self):
        return (
            f'<GameGoProSetup game_id={self.game_id} '
            f'position_id={self.position_id} cam_head="{self.cam_head_id}">'
        )

    def to_dict(self) -> dict:
        return {
            'id':            self.id,
            'game_id':       self.game_id,
            'position_id':   self.position_id,
            'position_name': self.position.name if self.position else None,
            'cam_head_id':   self.cam_head_id,
            'is_active':     self.is_active,
        }


def get_game_gopro_setup_model():
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_gopro_setups'
                and issubclass(cls, BaseGameGoProSetupMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy GameGoProSetup w rejestrze SQLAlchemy."
    )
