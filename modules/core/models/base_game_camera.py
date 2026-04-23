"""GameCamera model - Association between Game and Camera with location"""
from core.extensions import db
from datetime import datetime


# Stałe mapowanie: wejście HDMI karty przechwytującej → węzeł /dev/cameraN na Debianie.
# Kable HDMI są przepięte raz na stałe, więc mapowanie nie zmienia się między meczami.
# Slot 1 jest zawsze kamerą główną.
HDMI_TO_DEVICE: dict[int, str] = {
    1: "camera1",
    2: "camera2",
    3: "camera3",
    4: "camera4",
}

# Predefiniowane nazwy lokalizacji dla każdego wejścia HDMI.
# Używane jako wartość domyślna pola location gdy operator nie poda własnej nazwy.
HDMI_DEFAULT_LOCATION: dict[int, str] = {
    1: "Główna",
    2: "Centralna",
    3: "Lewa",
    4: "Prawa",
}

VALID_HDMI_INPUTS = tuple(HDMI_TO_DEVICE.keys())  # (1, 2, 3, 4)


class BaseGameCameraMixin:
    """
    Przypisanie fizycznej kamery do meczu.

    Operator wybiera:
      - camera_id  → która fizyczna kamera (z tabeli cameras)
      - location   → gdzie kamera jest ustawiona (opis słowny, np. "Za bramką północną")
      - hdmi_input → do którego wejścia HDMI karty przechwytującej jest podpięta (1–4)

    Na podstawie hdmi_input system automatycznie wie, który węzeł Debiana
    (/dev/cameraN) obsługuje nagrywanie — patrz HDMI_TO_DEVICE.

    Slot 1 (hdmi_input=1) jest z założenia kamerą główną.

    Ograniczenia unikalności (per mecz):
      - jedna kamera nie może być przypisana do dwóch wejść HDMI
      - do jednego wejścia HDMI nie można przypisać dwóch kamer
    """

    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'), nullable=False, index=True)

    # Opis słowny miejsca ustawienia kamery (np. "Za bramką północną", "Trybuny główne")
    location = db.Column(db.String(200), nullable=False)

    # Wejście HDMI karty przechwytującej: 1–4.
    # Slot 1 = kamera główna.
    # Mapowanie hdmi_input → /dev/cameraN zdefiniowane w HDMI_TO_DEVICE.
    hdmi_input = db.Column(db.Integer, nullable=False)

    # Czy kamera jest motoryczna (zdalna zmiana ujęcia)
    is_motorized = db.Column(db.Boolean, default=False, nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @db.declared_attr
    def __table_args__(cls):
        return (
        # Jedna kamera nie może być przypisana dwa razy do tego samego meczu
        db.UniqueConstraint('game_id', 'camera_id', name='unique_game_camera')
,
        # Do jednego wejścia HDMI nie można przypisać dwóch kamer w tym samym meczu
        db.UniqueConstraint('game_id', 'hdmi_input', name='unique_game_hdmi_input'),
        # hdmi_input musi być w zakresie 1–4
        db.CheckConstraint('hdmi_input >= 1 AND hdmi_input <= 4', name='check_hdmi_input_range'),
    )

    @property
    def device_name(self) -> str:
        """Węzeł /dev/cameraN na Debianie obsługujący ten slot HDMI."""
        return HDMI_TO_DEVICE[self.hdmi_input]

    @property
    def is_main_camera(self) -> bool:
        """Czy to kamera główna (slot HDMI 1)."""
        return self.hdmi_input == 1

    def __repr__(self):
        return (
            f'<GameCamera game_id={self.game_id} camera_id={self.camera_id} '
            f'location="{self.location}" hdmi_input={self.hdmi_input} device={self.device_name}>'
        )

    def to_dict(self):
        """Serializacja do słownika (np. dla API / hub messages)."""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'camera_id': self.camera_id,
            'camera_name': self.camera.name if self.camera else None,
            'location': self.location,
            'hdmi_input': self.hdmi_input,
            'device_name': self.device_name,
            'is_main_camera': self.is_main_camera,
            'is_motorized': self.is_motorized,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

def get_game_camera_model():
    """Zwraca klasę GameCamera zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'game_cameras'
                and issubclass(cls, BaseGameCameraMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy GameCamera w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
