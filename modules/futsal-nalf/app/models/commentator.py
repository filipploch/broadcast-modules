"""Commentator model - Game commentators"""
from app.extensions import db
from datetime import datetime


class Commentator(db.Model):
    """Football commentator"""
    __tablename__ = 'commentators'

    id = db.Column(db.Integer, primary_key=True)
    
    # Commentator info
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    game_commentators = db.relationship('GameCommentator', backref='commentator', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Commentator {self.first_name} {self.last_name}>'

    @property
    def full_name(self):
        """Get full name"""
        return f"{self.first_name} {self.last_name}"

    @property
    def short_name(self):
        """Get short name (first letter of first name + last name)"""
        return f"{self.first_name[0]}. {self.last_name}" if self.first_name else self.last_name

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': self.full_name,
            'short_name': self.short_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
