"""Stadium model - Football stadiums"""
from core.extensions import db
from datetime import datetime
from sqlalchemy.orm import declared_attr


class BaseStadiumMixin:
    """Football stadium"""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    city = db.Column(db.String(50), nullable=False, index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    @declared_attr
    def games(cls):
        return db.relationship('Game', backref='stadium', lazy='dynamic')

    # Composite unique constraint: name + city must be unique
    @db.declared_attr
    def __table_args__(cls):
        return (
        db.UniqueConstraint('name', 'city', name='uix_stadium_name_city')
,
    )

    def __repr__(self):
        return f'<Stadium {self.name}, {self.city}>'

    @property
    def full_address(self):
        """Get full formatted address"""
        return f"{self.address}, {self.city}"

    @property
    def total_games(self):
        """Get total number of games played at this stadium"""
        return self.games.count()

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'city': self.city,
            'full_address': self.full_address,
            'total_games': self.total_games,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

def get_stadium_model():
    """Zwraca klasę Stadium zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'stadiums'
                and issubclass(cls, BaseStadiumMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy Stadium w rejestrze SQLAlchemy. "
        "Upewnij się że model modułu jest zaimportowany przed wywołaniem."
    )
