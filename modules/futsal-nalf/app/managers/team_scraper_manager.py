"""Team Manager - handles CRUD operations and scraping workflow with threading"""
from typing import List, Dict, Optional, Callable
from flask import session, current_app
from app.extensions import db
from app.models.team import Team
from app.managers.team_manager import TeamManager
import threading
import logging
import os

logger = logging.getLogger(__name__)

team_manager = TeamManager()

class TeamScraperManager:
    """Manager for Team CRUD operations and scraping workflow"""
    
    SCRAPED_TEAMS_SESSION_KEY = 'scraped_teams'
    SCRAPING_STATUS_KEY = 'scraping_status'
    
    def __init__(self):
        self._scraping_thread = None
        self._scraping_lock = threading.Lock()
       
    # =========================
    # Scraping Workflow (Threaded)
    # =========================
    
    # def scrape_leagues_async(self, league_urls: List[str],
                            # callback: Optional[Callable] = None) -> bool:
        # """
        # Start scraping teams from league pages in a separate thread

        # IMPORTANT: This method runs scraping in background thread!
        # - Updates existing teams' names automatically
        # - Adds new teams to pending list

        # Args:
            # league_urls: List of league table URLs
            # callback: Optional callback function when scraping completes

        # Returns:
            # True if scraping started, False if already running
        # """
        # with self._scraping_lock:
            # if self._scraping_thread and self._scraping_thread.is_alive():
                # logger.warning("Scraping already in progress")
                # return False

            # # Set status to in_progress
            # session[self.SCRAPING_STATUS_KEY] = {
                # 'status': 'in_progress',
                # 'total_scraped': 0,
                # 'updated': 0,
                # 'new_pending': 0,
                # 'error': None
            # }
            # session.modified = True

            # # Start scraping in new thread
            # self._scraping_thread = threading.Thread(
                # target=self._scrape_worker,
                # args=(league_urls, callback),
                # daemon=True
            # )
            # self._scraping_thread.start()

            # logger.info(f"Started scraping in background thread for {len(league_urls)} URLs")
            # return True
    
    # def _scrape_worker(self, league_urls: List[str], callback: Optional[Callable] = None):
    def scrape_leagues_async(self, league_urls: List[str],
                             callback: Optional[Callable] = None):
        """
        Worker function that runs in separate thread
        
        Args:
            league_urls: List of URLs to scrape
            callback: Optional callback when done
        """
        # app = current_app._get_current_object()
        with current_app.app_context():

            try:
                # Import here to avoid circular imports
                from app.utils.scrapers import TeamScraper
                
                scraper = TeamScraper()
                
                logger.info("Scraping started in thread")
                
                # Scrape teams
                scraped_teams = scraper.scrape_multiple_leagues(league_urls)
                
                # Process scraped teams
                stats = self._process_scraped_teams(scraped_teams)
                
                # Update status
                session[self.SCRAPING_STATUS_KEY] = {
                    'status': 'completed',
                    'total_scraped': stats['total_scraped'],
                    'updated': stats['updated'],
                    'new_pending': stats['new_pending'],
                    'error': None
                }
                session.modified = True
                
                logger.info(
                    f"Scraping completed: {stats['total_scraped']} total, "
                    f"{stats['updated']} updated, {stats['new_pending']} new"
                )
                
                # Call callback if provided
                if callback:
                    callback(stats)
                    
            except Exception as e:
                logger.error(f"Scraping error in thread: {e}", exc_info=True)

                # Update status with error
                session[self.SCRAPING_STATUS_KEY] = {
                    'status': 'error',
                    'total_scraped': 0,
                    'updated': 0,
                    'new_pending': 0,
                    'error': str(e)
                }
                session.modified = True
    
    def get_scraping_status(self) -> Dict:
        """
        Get current scraping status
        
        Returns:
            Dictionary with status info:
            {
                'status': 'idle' | 'in_progress' | 'completed' | 'error',
                'total_scraped': int,
                'updated': int,
                'new_pending': int,
                'error': str | None
            }
        """
        return session.get(self.SCRAPING_STATUS_KEY, {
            'status': 'idle',
            'total_scraped': 0,
            'updated': 0,
            'new_pending': 0,
            'error': None
        })
    
    def clear_scraping_status(self):
        """Clear scraping status from session"""
        session.pop(self.SCRAPING_STATUS_KEY, None)
        session.modified = True
    
    def _process_scraped_teams(self, scraped_teams: List[Dict[str, str]]) -> Dict[str, int]:
        """
        Process scraped teams: update existing teams' names and collect new teams
        
        CRITICAL: This updates the 'name' field for existing teams automatically!
        
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
            
            # Check if team exists in database
            existing_team = team_manager.get_team_by_url(team_url)
            
            if existing_team:
                # Team exists → ALWAYS update name (names can change)
                if existing_team.name != team_name:
                    old_name = existing_team.name
                    existing_team.name = team_name
                    db.session.commit()
                    updated_count += 1
                    logger.info(f"Updated team name: '{old_name}' → '{team_name}'")
                else:
                    logger.debug(f"Team name unchanged: {team_name}")
            else:
                # Team is new → add to pending list
                new_teams.append(team_data)
        
        # Store new teams in session
        session[self.SCRAPED_TEAMS_SESSION_KEY] = new_teams
        session.modified = True
        
        return {
            'total_scraped': len(scraped_teams),
            'updated': updated_count,
            'new_pending': len(new_teams)
        }
    
    # def get_pending_teams(self) -> List[Dict[str, str]]:
    def get_pending_teams(self):
        """
        Get list of scraped teams pending completion
        
        Returns:
            List of team dictionaries from session
        """
        return session.get(self.SCRAPED_TEAMS_SESSION_KEY, [])
    
    def get_pending_team_by_url(self, team_url: str) -> Optional[Dict[str, str]]:
        """
        Get specific pending team by URL
        
        Args:
            team_url: Team URL
        
        Returns:
            Team dictionary or None if not found
        """
        pending_teams = self.get_pending_teams()
        for team in pending_teams:
            if team['team_url'] == team_url:
                return team
        return None
    
    def remove_pending_team(self, team_url: str) -> bool:
        """
        Remove team from pending list in session
        
        Args:
            team_url: Team URL to remove
        
        Returns:
            True if removed, False if not found
        """
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
    
    def complete_team_from_scraping(self, team_url: str, name_20: str, 
                                   short_name: str, logo_path: str = None,
                                   foreign_id: str = None) -> Optional[Team]:
        """
        Complete a scraped team with additional data and save to database
        
        Args:
            team_url: Team URL (from scraped data)
            name_20: Shortened name (max 20 chars)
            short_name: 3-letter abbreviation
            logo_path: Optional logo path (defaults to default.png)
            foreign_id: Optional external ID (auto-extracted from team_url if not provided)
        
        Returns:
            Created Team object or None if scraped data not found
        """
        # Get scraped team data
        pending_team = self.get_pending_team_by_url(team_url)
        if not pending_team:
            logger.warning(f"No pending team found with URL: {team_url}")
            return None
        
        # Check if team already exists (safety check)
        existing_team = team_manager.get_team_by_url(team_url)
        if existing_team:
            logger.warning(f"Team already exists: {existing_team.name}")
            self.remove_pending_team(team_url)
            return existing_team
        
        # Auto-extract foreign_id from team_url if not provided
        if foreign_id is None and 'sp_team=' in team_url:
            foreign_id = team_url.split('sp_team=')[1]
            logger.info(f"Auto-extracted foreign_id: {foreign_id}")
        
        # Create team with complete data
        if logo_path is None:
            logo_path = 'static/images/logos/default.png'
        
        team = team_manager.create_team(
            name=pending_team['name'],
            name_20=name_20,
            short_name=short_name,
            team_url=team_url,
            logo_path=logo_path,
            foreign_id=foreign_id
        )
        
        # Remove from pending list
        self.remove_pending_team(team_url)
        
        return team
    
    # =========================
    # Helper Methods
    # =========================
    
    def get_statistics(self) -> Dict[str, int]:
        """
        Get statistics about teams
        
        Returns:
            Dictionary with counts
        """
        total_teams = Team.query.count()
        pending_teams = len(self.get_pending_teams())
        
        return {
            'total_teams': total_teams,
            'pending_teams': pending_teams
        }
    
    def is_scraping_in_progress(self) -> bool:
        """Check if scraping is currently running"""
        status = self.get_scraping_status()
        return status['status'] == 'in_progress'