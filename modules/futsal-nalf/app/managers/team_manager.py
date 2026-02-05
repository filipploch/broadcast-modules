"""Team Manager - handles CRUD operations and scraping workflow with threading"""
from typing import List, Dict, Optional, Callable
from flask import session, current_app
from app.extensions import db
from app.models.team import Team
import threading
import logging
import os

logger = logging.getLogger(__name__)


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
        logos_dir = os.path.join(current_app.static_folder, 'images', 'logos')
        logos = []

        if os.path.exists(logos_dir):
            allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
            for file in os.listdir(logos_dir):
                print(f'file: {file}')
                if any(file.lower().endswith(ext) for ext in allowed_extensions):
                    logos.append({
                        'filename': file,
                        'path': f'/static/images/logos/{file}'
                    })
        return logos
    
    def get_all_teams(self) -> List[Team]:
        """Get all teams from database"""
        return Team.query.order_by(Team.name).all()
    
    def get_team_by_id(self, team_id: int) -> Optional[Team]:
        """Get team by ID"""
        return Team.query.get(team_id)
    
    def get_team_by_url(self, team_url: str) -> Optional[Team]:
        """Get team by team_url (unique identifier)"""
        return Team.query.filter_by(team_url=team_url).first()
    
    def create_team(self, name: str, name_20: str, short_name: str, 
                   team_url: str, logo_path: str = 'static/images/logos/default.png') -> Team:
        """
        Create new team
        
        Args:
            name: Full team name
            name_20: Shortened name (max 20 chars)
            short_name: 3-letter abbreviation
            team_url: Unique URL from NALF
            logo_path: Path to logo image
        
        Returns:
            Created Team object
        """
        team = Team(
            name=name,
            name_20=name_20,
            short_name=short_name.upper(),
            team_url=team_url,
            logo_path=logo_path
        )
        
        db.session.add(team)
        db.session.commit()
        
        logger.info(f"Created team: {team.name} ({team.short_name})")
        return team
    
    def update_team(self, team_id: int, **kwargs) -> Optional[Team]:
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
        
        allowed_fields = ['name', 'name_20', 'short_name', 'team_url', 'logo_path']
        
        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                if field == 'short_name':
                    value = value.upper()
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
