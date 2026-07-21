"""BaseCameraRecordingSegmentMixin — jeden ciągły plik nagrania jednej kamery.

Pozwala odtworzyć, "który plik nagrywała kamera X o godzinie ściennej T" —
potrzebne do zamiany dowolnie wybranego czasu meczowego (patrz
BaseTimerSampleMixin) na konkretny plik + offset w sekundach.

recorder_camera_id to identyfikator SLOTU HDMI karty przechwytującej
("camera1".."camera4", patrz core.models.base_game_camera.HDMI_TO_DEVICE) —
NIE klucz obcy do tabeli cameras. Okablowanie HDMI jest przepięte na stałe,
więc ten string jest stabilną tożsamością nagrywającego urządzenia
niezależnie od tego, która fizyczna Camera/GameCamera jest logicznie
przypisana do tego slotu w danym meczu.

started_at/ended_at to czas ŚCIENNY (UTC) odebrania sygnału przez serwer
main-module (nie czas zgłoszony przez sam recorder-plugin) — dzięki temu
mechanizm nie zależy od zgodności zegarów między maszynami, tylko od
opóźnienia sieciowego plugin→serwer (pomijalne w sieci lokalnej).
reported_started_at to wartość zgłoszona przez plugin, trzymana wyłącznie
do diagnostyki ewentualnego rozjazdu zegarów.
"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseCameraRecordingSegmentMixin:

    id = db.Column(db.Integer, primary_key=True)

    recorder_camera_id = db.Column(db.String(50), nullable=False, index=True)

    @declared_attr
    def game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=True, index=True)

    @declared_attr
    def period_id(cls):
        return db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=True, index=True)

    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=True)

    started_at = db.Column(db.DateTime, nullable=False, index=True)
    ended_at   = db.Column(db.DateTime, nullable=True, index=True)  # NULL = wciąż nagrywa

    reported_started_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @declared_attr
    def game(cls):
        return db.relationship('Game')

    @declared_attr
    def period(cls):
        return db.relationship('Period')

    def __repr__(self):
        return (f'<CameraRecordingSegment {self.recorder_camera_id} '
                f'game_id={self.game_id} {self.file_name} '
                f'{"open" if self.ended_at is None else "closed"}>')

    def to_dict(self):
        return {
            'id': self.id,
            'recorder_camera_id': self.recorder_camera_id,
            'game_id': self.game_id,
            'period_id': self.period_id,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
        }

    @classmethod
    def open_segment_for_camera(cls, recorder_camera_id):
        """Aktualnie otwarty (wciąż nagrywający) segment tej kamery, jeśli jest."""
        return (cls.query
                .filter_by(recorder_camera_id=recorder_camera_id, ended_at=None)
                .order_by(cls.started_at.desc())
                .first())

    @classmethod
    def start_segment(cls, recorder_camera_id, game_id, period_id,
                       file_name, file_path=None, reported_started_at=None):
        """
        Zamknij ewentualny wciąż otwarty poprzedni segment tej kamery (siatka
        bezpieczeństwa — gdyby sygnał recording_stopped się zgubił, np. przy
        crashu obsłużonym inną ścieżką) i otwórz nowy.
        """
        cls.close_open_segment(recorder_camera_id)
        row = cls(
            recorder_camera_id=recorder_camera_id,
            game_id=game_id,
            period_id=period_id,
            file_name=file_name,
            file_path=file_path,
            started_at=datetime.utcnow(),
            reported_started_at=reported_started_at,
        )
        db.session.add(row)
        db.session.commit()
        return row

    @classmethod
    def close_open_segment(cls, recorder_camera_id, ended_at=None):
        row = cls.open_segment_for_camera(recorder_camera_id)
        if row:
            row.ended_at = ended_at or datetime.utcnow()
            db.session.commit()
        return row

    @classmethod
    def find_at(cls, recorder_camera_id, game_id, wall_clock):
        """Segment tej kamery (w tym meczu) obejmujący podany czas ścienny."""
        return (cls.query
                .filter(
                    cls.recorder_camera_id == recorder_camera_id,
                    cls.game_id == game_id,
                    cls.started_at <= wall_clock,
                    db.or_(cls.ended_at.is_(None), cls.ended_at >= wall_clock),
                )
                .order_by(cls.started_at.desc())
                .first())

    @classmethod
    def cameras_for_game(cls, game_id):
        """Lista distinct recorder_camera_id, które kiedykolwiek nagrywały ten mecz."""
        rows = (db.session.query(cls.recorder_camera_id)
                .filter_by(game_id=game_id)
                .distinct()
                .all())
        return [r[0] for r in rows]


def get_camera_recording_segment_model():
    """Zwraca konkretną klasę BaseCameraRecordingSegmentMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'camera_recording_segments'
                and issubclass(cls, BaseCameraRecordingSegmentMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseCameraRecordingSegmentMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_camera_recording_segment_model()."
    )
