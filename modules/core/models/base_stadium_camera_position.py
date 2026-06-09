"""StadiumCameraPosition — predefiniowane miejsce montażu kamery GoPro na obiekcie."""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


# Domyślne pozycje kamer dla obiektów z układem boiskowym (zone_scheme = FIELD_GRID).
# Używane przez seed_field_positions().
FIELD_GRID_POSITION_DEFAULTS = [
    {'code': 'CC',  'name': 'Kamera centralna - bliższa',    'description': 'Kamera po środku bliższej linii bocznej',           'sort_order': 0},
    {'code': 'LC',  'name': 'Kamera lewa - bliższa',         'description': 'Kamera po lewej stronie bliższej linii bocznej',    'sort_order': 1},
    {'code': 'RC',  'name': 'Kamera prawa - bliższa',        'description': 'Kamera po prawej stronie bliższej linii bocznej',   'sort_order': 2},
    {'code': 'LCC', 'name': 'Kamera w lewym bliższym rogu',  'description': 'Kamera w lewym rogu przy bliższej linii końcowej',  'sort_order': 3},
    {'code': 'RCC', 'name': 'Kamera w prawym bliższym rogu', 'description': 'Kamera w prawym rogu przy bliższej linii końcowej', 'sort_order': 4},
    {'code': 'LG',  'name': 'Kamera za bramką lewą',         'description': 'Kamera ustawiona za bramką po lewej stronie',       'sort_order': 5},
    {'code': 'RG',  'name': 'Kamera za bramką prawą',        'description': 'Kamera ustawiona za bramką po prawej stronie',      'sort_order': 6},
    {'code': 'CF',  'name': 'Kamera centralna - dalsza',     'description': 'Kamera po środku dalszej linii bocznej',            'sort_order': 7},
    {'code': 'LF',  'name': 'Kamera lewa - dalsza',          'description': 'Kamera po lewej stronie dalszej linii bocznej',     'sort_order': 8},
    {'code': 'RF',  'name': 'Kamera prawa - dalsza',         'description': 'Kamera po prawej stronie dalszej linii bocznej',    'sort_order': 9},
    {'code': 'LCF', 'name': 'Kamera w lewym dalszym rogu',   'description': 'Kamera w lewym rogu przy dalszej linii końcowej',   'sort_order': 10},
    {'code': 'RCF', 'name': 'Kamera w prawym dalszym rogu',  'description': 'Kamera w prawym rogu przy dalszej linii końcowej',  'sort_order': 11},
]


class BaseStadiumCameraPositionMixin:
    """
    Fizyczne miejsce, w którym można zamontować głowicę pan/tilt z kamerą GoPro.

    Każdy obiekt ma własny zestaw pozycji (np. "Narożnik NE", "Za bramką Południe").
    Do każdej pozycji przypisana jest kalibracja pan/tilt dla stref obiektu
    (tabela camera_position_calibrations). Schemat stref określa pole zone_scheme w stadiums.

    Dla obiektów FIELD_GRID istnieją predefiniowane kody pozycji (CC, LC, LG, ...).
    Można je wstawić jednorazowo za pomocą seed_field_positions(stadium_id).
    """

    id          = db.Column(db.Integer, primary_key=True)
    stadium_id  = db.Column(db.Integer, db.ForeignKey('stadiums.id'), nullable=False, index=True)
    # Schemat stref — lustrzane odbicie stadiums.zone_scheme; pozwala filtrować bez JOIN
    zone_scheme = db.Column(db.String(20), nullable=False, default='FIELD_GRID', server_default='FIELD_GRID')
    # Krótki kod pozycji (CC, LC, LG, …). NULL dla tras/torów (TRACK_LINEAR).
    code        = db.Column(db.String(3), nullable=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sort_order  = db.Column(db.Integer, nullable=False, default=0)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
            # NULL-y nie łamią unique — wiele pozycji bez kodu może istnieć obok siebie
            db.UniqueConstraint('stadium_id', 'code', name='uix_stadium_camera_position_code'),
        )

    def get_aim(self, zone_code: str) -> tuple[int, int] | None:
        """Zwraca (pan, tilt) dla podanej strefy, lub None jeśli brak kalibracji."""
        cal = self.calibrations.filter_by(zone_code=zone_code).first()
        return (cal.pan, cal.tilt) if cal else None

    def __repr__(self):
        return f'<StadiumCameraPosition stadium_id={self.stadium_id} code={self.code!r} name="{self.name}">'

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'stadium_id':  self.stadium_id,
            'zone_scheme': self.zone_scheme,
            'code':        self.code,
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


def seed_field_positions(stadium_id: int) -> list:
    """
    Wstawia domyślne pozycje kamer FIELD_GRID dla podanego stadionu,
    pomijając te, których kod już istnieje w tabeli.
    Zwraca listę nowo utworzonych obiektów (może być pusta).

    Wywołaj jednorazowo po utworzeniu nowego stadionu z zone_scheme = FIELD_GRID,
    lub przy starcie aplikacji dla istniejących stadionów bez pozycji.
    """
    from core.extensions import db

    StadiumCameraPosition = get_stadium_camera_position_model()

    existing_codes = {
        row.code
        for row in StadiumCameraPosition.query
            .filter_by(stadium_id=stadium_id)
            .with_entities(StadiumCameraPosition.code)
            .all()
        if row.code is not None
    }

    created = []
    for defaults in FIELD_GRID_POSITION_DEFAULTS:
        if defaults['code'] not in existing_codes:
            pos = StadiumCameraPosition(stadium_id=stadium_id, zone_scheme='FIELD_GRID', **defaults)
            db.session.add(pos)
            created.append(pos)

    if created:
        db.session.commit()

    return created
