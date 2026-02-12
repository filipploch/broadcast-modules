"""Settings model - Application global settings"""
from app.extensions import db
from datetime import datetime


class Settings(db.Model):
    """Global application settings - singleton table"""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    current_season_id = db.Column(db.Integer, db.ForeignKey('seasons.id'), nullable=True)
    current_game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=True)
    current_period_id = db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    current_season = db.relationship('Season', foreign_keys=[current_season_id], backref='settings_ref')
    current_game = db.relationship('Game', foreign_keys=[current_game_id], backref='settings_ref')
    current_period = db.relationship('Period', foreign_keys=[current_period_id], backref='settings_ref')

    def __repr__(self):
        return f'<Settings season_id={self.current_season_id} game_id={self.current_game_id} period_id={self.current_period_id}>'

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
    def set_current_season(cls, season_id):
        """Set current active season"""
        settings = cls.get_settings()
        settings.current_season_id = season_id
        settings.updated_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def set_current_game(cls, game_id):
        """Set current active game"""
        settings = cls.get_settings()
        settings.current_game_id = game_id
        settings.updated_at = datetime.utcnow()
        db.session.commit()
    
    @classmethod
    def set_current_period(cls, period_id):
        """Set current active period"""
        settings = cls.get_settings()
        settings.current_period_id = period_id
        settings.updated_at = datetime.utcnow()
        db.session.commit()
    
    @classmethod
    def validate_period_for_game(cls):
        """
        Validate that current_period_id belongs to current_game_id
        Returns True if valid or if period_id is None
        """
        settings = cls.get_settings()
        
        if settings.current_period_id is None:
            return True
        
        if settings.current_game_id is None:
            return False
        
        # Check if period belongs to the game
        from app.models.period import Period
        period = Period.query.get(settings.current_period_id)
        
        if not period:
            return False
        
        return period.game_id == settings.current_game_id