"""Team Manager - handles CRUD operations and scraping workflow with threading"""
from typing import List, Dict, Optional
from flask import session
from core.extensions import db
from app.models.team import Team
from app.models.scraper import Scraper
from core.managers.team_manager import TeamManager
import threading
import logging

logger = logging.getLogger(__name__)

team_manager = TeamManager()


def _get_scraper_id():
    scraper = Scraper.get_by_folder('laczynaspilka')
    if not scraper:
        raise RuntimeError("Scraper 'laczynaspilka' nie jest zarejestrowany w tabeli scrapers")
    return scraper.id


class TeamScraperManager:
    """Manager for Team CRUD operations and scraping workflow"""

    SCRAPED_TEAMS_SESSION_KEY = 'scraped_teams'

    def __init__(self):
        self._scraping_thread = None
        self._scraping_lock = threading.Lock()
        self._status: Dict = {
            'status': 'idle',
            'total_scraped': 0,
            'updated': 0,
            'new_pending': 0,
            'error': None
        }

    # =========================
    # Scraping Workflow (Threaded)
    # =========================
    # NOTE: no scraper is currently wired up here — garbarnia has no
    # dedicated team-list scraper (the old team_scraper.py was an
    # unused nalffutsal.pl copy-paste, removed). _process_scraped_teams
    # below stays ready for whichever scraper eventually calls it.

    def get_scraping_status(self) -> Dict:
        """Get current scraping status."""
        return self._status.copy()

    def clear_scraping_status(self):
        """Reset status to idle"""
        self._status = {
            'status': 'idle',
            'total_scraped': 0,
            'updated': 0,
            'new_pending': 0,
            'error': None
        }

    def is_scraping_in_progress(self) -> bool:
        """Check if scraping is currently running"""
        return self._status['status'] == 'in_progress'

    # =========================
    # Processing
    # =========================

    def _process_scraped_teams(self, scraped_teams: List[Dict[str, str]]) -> Dict[str, int]:
        """
        Process scraped teams: update existing teams' names and collect new teams.

        Args:
            scraped_teams: List of team dictionaries from scraper

        Returns:
            Statistics dictionary
        """
        updated_count = 0
        new_teams = []

        for team_data in scraped_teams:
            team_url = team_data['team_url']
            team_name = team_data['name']

            existing_team = team_manager.get_team_by_url(team_url)

            if existing_team:
                if existing_team.name != team_name:
                    old_name = existing_team.name
                    existing_team.name = team_name
                    db.session.commit()
                    updated_count += 1
                    logger.info(f"Updated team name: '{old_name}' → '{team_name}'")
                else:
                    logger.debug(f"Team name unchanged: {team_name}")
            else:
                new_teams.append(team_data)

        session[self.SCRAPED_TEAMS_SESSION_KEY] = new_teams
        session.modified = True

        return {
            'total_scraped': len(scraped_teams),
            'updated': updated_count,
            'new_pending': len(new_teams)
        }

    # =========================
    # Pending teams
    # =========================

    def get_pending_teams(self):
        """Get list of scraped teams pending completion"""
        return session.get(self.SCRAPED_TEAMS_SESSION_KEY, [])

    def get_pending_team_by_url(self, team_url: str) -> Optional[Dict[str, str]]:
        """Get specific pending team by URL"""
        pending_teams = self.get_pending_teams()
        for team in pending_teams:
            if team['team_url'] == team_url:
                return team
        return None

    def remove_pending_team(self, team_url: str) -> bool:
        """Remove team from pending list in session"""
        pending_teams = self.get_pending_teams()
        updated_teams = [t for t in pending_teams if t['team_url'] != team_url]

        if len(updated_teams) < len(pending_teams):
            session[self.SCRAPED_TEAMS_SESSION_KEY] = updated_teams
            session.modified = True
            return True

        return False

    def clear_pending_teams(self):
        """Clear all pending teams from session"""
        session.pop(self.SCRAPED_TEAMS_SESSION_KEY, None)
        session.modified = True

    def complete_team_from_scraping(self, team_url: str, name_14: str,
                                   short_name: str, logo_path: str = None,
                                   foreign_id: str = None) -> Optional[Team]:
        """Complete a scraped team with additional data and save to database"""
        pending_team = self.get_pending_team_by_url(team_url)
        if not pending_team:
            logger.warning(f"No pending team found with URL: {team_url}")
            return None

        existing_team = team_manager.get_team_by_url(team_url)
        if existing_team:
            logger.warning(f"Team already exists: {existing_team.name}")
            self.remove_pending_team(team_url)
            return existing_team

        if foreign_id is None and 'sp_team=' in team_url:
            foreign_id = team_url.split('sp_team=')[1]
            logger.info(f"Auto-extracted foreign_id: {foreign_id}")

        if logo_path is None:
            logo_path = 'static/images/logos/default.png'

        team = team_manager.create_team(
            name=pending_team['name'],
            name_14=name_14,
            short_name=short_name,
            team_url=team_url,
            logo_path=logo_path,
        )
        if foreign_id:
            team_manager.set_team_foreign_id(team.id, _get_scraper_id(), foreign_id)

        self.remove_pending_team(team_url)
        return team

    # =========================
    # Helper Methods
    # =========================

    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about teams"""
        total_teams = Team.query.count()
        pending_teams = len(self.get_pending_teams())

        return {
            'total_teams': total_teams,
            'pending_teams': pending_teams
        }
