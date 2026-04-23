"""Team Manager - handles CRUD operations and scraping workflow with threading"""
from flask import session, current_app
from core.extensions import db
import threading
import logging
import os

logger = logging.getLogger(__name__)

def _get_team():
    from core.models.base_team import get_team_model
    return get_team_model()

class TeamManager:
    """Manager for Team CRUD operations and scraping workflow"""
    
    # SCRAPED_TEAMS_SESSION_KEY = 'scraped_teams'
    # SCRAPING_STATUS_KEY = 'scraping_status'
    
    def __init__(self):
        # self._scraping_thread = None
        # self._scraping_lock = threading.Lock()
        self.logos = self.get_all_logos()
    
    # =========================
    # CRUD Operations
    # =========================

    def get_all_logos(self):
        with current_app.app_context():
            module_name = current_app.config['MODULE_NAME']
        logos_dir = os.path.join(current_app.static_folder, 'images', 'logos', module_name)
        logos = []

        if os.path.exists(logos_dir):
            allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
            for file in os.listdir(logos_dir):
                if any(file.lower().endswith(ext) for ext in allowed_extensions):
                    logos.append({
                        'filename': file,
                        'path': f'/static/images/logos/{module_name}/{file}'
                    })
        return logos
    
    def get_all_teams(self):
        """Get all teams from database"""
        Team = _get_team()
        return Team.query.order_by(Team.name).all()
    
    def get_team_by_id(self, team_id: int):
        """Get team by ID"""
        Team = _get_team()
        return Team.query.get(team_id)
    
    def get_team_by_url(self, team_url: str):
        """Get team by team_url (unique identifier)"""
        Team = _get_team()
        return Team.query.filter_by(team_url=team_url).first()
    
    def get_team_by_name(self, name: str):
        """Get team by team_url (unique identifier)"""
        Team = _get_team()
        return Team.query.filter_by(name=name).first()
    
    def create_team(self, name: str, name_14: str, short_name: str, 
                   team_url: str, logo_path: str = 'static/images/logos/default.png',
                   foreign_id: str = None, coach: str = None, uniform: dict = None):
        """
        Create new team
        
        Args:
            name: Full team name
            name_14: Shortened name (max 20 chars)
            short_name: 3-letter abbreviation
            team_url: Unique URL from NALF
            logo_path: Path to logo image
            foreign_id: Optional external ID for integration
        
        Returns:
            Created Team object
        """
        import json
        Team = _get_team()
        team = Team(
            name=name,
            name_14=name_14,
            short_name=short_name.upper(),
            team_url=team_url,
            logo_path=logo_path,
            foreign_id=foreign_id,
            uniform=json.dumps(uniform) if uniform else None
        )
        
        db.session.add(team)
        db.session.commit()
        
        logger.info(f"Created team: {team.name} ({team.short_name})")
        return team
    
    def update_team(self, team_id: int, **kwargs):
        """
        Update team
        
        Args:
            team_id: Team ID
            **kwargs: Fields to update
        
        Returns:
            Updated Team object or None if not found
        """
        team = self.get_team_by_id(team_id)
        if not team:
            return None
        
        allowed_fields = ['name', 'coach', 'name_14', 'short_name', 'team_url', 'logo_path', 'uniform']
        
        import json
        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                if field == 'short_name':
                    value = value.upper()
                elif field == 'uniform':
                    value = json.dumps(value) if isinstance(value, dict) else value
                setattr(team, field, value)
        
        db.session.commit()
        logger.info(f"Updated team: {team.name}")
        return team
    
    def delete_team(self, team_id: int) -> bool:
        """
        Delete team
        
        Args:
            team_id: Team ID
        
        Returns:
            True if deleted, False if not found
        """
        team = self.get_team_by_id(team_id)
        if not team:
            return False
        
        team_name = team.name
        db.session.delete(team)
        db.session.commit()
        
        logger.info(f"Deleted team: {team_name}")
        return True