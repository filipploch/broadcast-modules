"""GameCamera model - Association between Game and Camera with location"""
from app.extensions import db
from datetime import datetime


class GameCamera(db.Model):
    """Association between Game and Camera with specific location"""
    __tablename__ = 'game_cameras'

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'), nullable=False, index=True)
    
    # Location (can be JSON reference or relation to separate table)
    # For now using string field for flexibility - can reference JSON file or be a simple string
    location = db.Column(db.String(200), nullable=False)
    
    # Camera settings for this game
    is_motorized = db.Column(db.Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one camera can only be at one location per game
    __table_args__ = (
        db.UniqueConstraint('game_id', 'camera_id', name='unique_game_camera'),
        db.UniqueConstraint('game_id', 'location', name='unique_game_location'),
    )

    def __repr__(self):
        return f'<GameCamera game_id={self.game_id} camera_id={self.camera_id} location={self.location}>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'camera_id': self.camera_id,
            'camera_name': self.camera.name if self.camera else None,
            'location': self.location,
            'is_motorized': self.is_motorized,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
