"""Camera model - Camera equipment used in games"""
from app.extensions import db
from datetime import datetime


class Camera(db.Model):
    """Camera equipment (physical camera device)"""
    __tablename__ = 'cameras'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(100), nullable=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    game_cameras = db.relationship('GameCamera', backref='camera', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Camera {self.name} ({self.brand} {self.model})>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'brand': self.brand,
            'model': self.model,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
