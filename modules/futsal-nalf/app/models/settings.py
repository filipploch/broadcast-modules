"""Settings model - Application global settings"""
from app.extensions import db
from datetime import datetime


class Settings(db.Model):
    """Global application settings - singleton table"""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    actual_season_id = db.Column(db.Integer, db.ForeignKey('seasons.id'), nullable=True)
    actual_game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    actual_season = db.relationship('Season', foreign_keys=[actual_season_id], backref='settings_ref')
    actual_game = db.relationship('Game', foreign_keys=[actual_game_id], backref='settings_ref')

    def __repr__(self):
        return f'<Settings season_id={self.actual_season_id} game_id={self.actual_game_id}>'

    @classmethod
    def get_settings(cls):
        """Get or create singleton settings instance"""
        settings = cls.query.first()
        if not settings:
            settings = cls()
            db.session.add(settings)
            db.session.commit()
        return settings

    @classmethod
    def set_actual_season(cls, season_id):
        """Set current active season"""
        settings = cls.get_settings()
        settings.actual_season_id = season_id
        settings.updated_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def set_actual_game(cls, game_id):
        """Set current active game"""
        settings = cls.get_settings()
        settings.actual_game_id = game_id
        settings.updated_at = datetime.utcnow()
        db.session.commit()