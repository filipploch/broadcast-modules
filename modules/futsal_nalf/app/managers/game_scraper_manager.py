"""Game Scraper Manager - handles CRUD operations and scraping workflow with threading"""
from typing import List, Dict, Optional, Callable
from flask import session, current_app
from core.extensions import db
from core.models.team import Team
from core.models.game import Game
from app.managers.team_manager import TeamManager
from core.managers.game_manager import GameManager
# from app.managers import get_game_manager
from datetime import datetime
import threading
import logging

logger = logging.getLogger(__name__)

team_manager = TeamManager()
game_manager = GameManager()


class GameScraperManager:
    """Manager for Game CRUD operations and scraping workflow"""

    SCRAPED_GAMES_SESSION_KEY = 'scraped_games'

    def __init__(self):
        self._scraping_thread = None
        self._scraping_lock = threading.Lock()
        # In-memory status — survives across requests, works from background threads
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

    def scrape_games_async(self, league_urls: List[str], league_name: str = '') -> bool:
        """
        Start scraping games in a background thread.

        Args:
            league_urls: List of URLs to scrape
            league_name: Human-readable league name for socket payloads

        Returns:
            True if scraping started, False if already running
        """
        with self._scraping_lock:
            if self._scraping_thread and self._scraping_thread.is_alive():
                logger.warning("Scraping already in progress")
                return False

            self._status = {
                'status': 'in_progress',
                'total_scraped': 0,
                'updated': 0,
                'new_pending': 0,
                'error': None
            }

            app = current_app._get_current_object()
            self._scraping_thread = threading.Thread(
                target=self._scrape_worker,
                args=(app, league_urls, league_name),
                daemon=True
            )
            self._scraping_thread.start()

            from core.extensions import socketio
            socketio.emit('scraping_started', {'name': league_name})

            logger.info(f"Started scraping in background thread for {len(league_urls)} URLs")
            return True

    def _scrape_worker(self, app, league_urls: List[str], league_name: str = ''):
        """Background worker — runs in a separate thread."""
        with app.app_context():
            from core.extensions import socketio
            try:
                from app.managers.scrapers import GameScraper

                scraper = GameScraper()
                logger.info("Scraping started in thread")

                scraped_games = scraper.scrape_multiple_leagues(league_urls)
                stats = self._process_scraped_games(scraped_games)

                self._status = {
                    'status': 'completed',
                    'total_scraped': stats['total_scraped'],
                    'updated': stats['updated'],
                    'new_pending': stats['new_pending'],
                    'error': None
                }

                logger.info(
                    f"Scraping completed: {stats['total_scraped']} total, "
                    f"{stats['updated']} updated, {stats['new_pending']} new"
                )

                socketio.emit('scraping_completed', {
                    'status': 'success',
                    'name': league_name,
                    'total_scraped': stats['total_scraped'],
                    'updated': stats['updated'],
                    'new_pending': stats['new_pending'],
                })

            except Exception as e:
                logger.error(f"Scraping error in thread: {e}", exc_info=True)
                self._status = {
                    'status': 'error',
                    'total_scraped': 0,
                    'updated': 0,
                    'new_pending': 0,
                    'error': str(e)
                }

                socketio.emit('scraping_error', {'status': 'error', 'name': league_name, 'error': str(e)})

    def get_scraping_status(self) -> Dict:
        """
        Get current scraping status.

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

    def _process_scraped_games(self, scraped_games: List[Dict[str, str]]) -> Dict[str, int]:
        """
        Process scraped games: update existing games if data changed, insert new ones.

        Iterates over all scraped games, compares each with the existing DB record
        (matched by foreign_id) and updates only fields that have changed.
        New games are inserted as-is.

        Args:
            scraped_games: List of game dictionaries from scraper

        Returns:
            Statistics dictionary
        """
        date_format = '%Y-%m-%d %H:%M:%S%z'
        updated_count = 0
        new_games = []

        for game_data in scraped_games:
            foreign_id = game_data['foreign_id']

            home_team = team_manager.get_team_by_name(game_data['home_team_name'])
            away_team = team_manager.get_team_by_name(game_data['away_team_name'])
            if not home_team or not away_team:
                logger.warning(
                    f"Skipping game foreign_id={foreign_id}: "
                    f"team not found ({game_data['home_team_name']} / {game_data['away_team_name']})"
                )
                continue

            home_team_id = home_team.id
            away_team_id = away_team.id
            home_team_goals = game_data['home_team_goals']
            away_team_goals = game_data['away_team_goals']
            status = game_data['status']
            league_id = game_data['league_id']
            parsed_date = datetime.strptime(game_data['date'].replace('T', ' '), date_format)
            round_nr = game_data['round']

            existing_game = game_manager.get_game_by_foreign_id(foreign_id)

            if existing_game:
                # Skip update if www says Not Started but DB has a more advanced status
                # (Pending/Finished) — DB data is considered more up-to-date
                www_not_started = (status == Game.STATUS_NOT_STARTED)
                db_more_advanced = (existing_game.status != Game.STATUS_NOT_STARTED)
                if www_not_started and db_more_advanced:
                    logger.debug(
                        f"Skipping game foreign_id={foreign_id}: "
                        f"www=Not Started but db status={existing_game.status}, db is more up-to-date"
                    )
                    continue

                changes = {
                    'home_team_id':    (existing_game.home_team_id,    home_team_id),
                    'away_team_id':    (existing_game.away_team_id,    away_team_id),
                    'home_team_goals': (existing_game.home_team_goals, home_team_goals),
                    'away_team_goals': (existing_game.away_team_goals, away_team_goals),
                    'status':          (existing_game.status,          status),
                    'league_id':       (existing_game.league_id,       league_id),
                    'round':           (existing_game.round,           round_nr),
                    'date':            (existing_game.date,            parsed_date),
                }

                changed_fields = [
                    field for field, (old_val, new_val) in changes.items()
                    if old_val != new_val
                ]

                if changed_fields:
                    for field in changed_fields:
                        setattr(existing_game, field, changes[field][1])
                    logger.info(
                        f"Updated game foreign_id={foreign_id}, "
                        f"changed fields: {changed_fields}"
                    )
                    updated_count += 1
                else:
                    logger.debug(f"No changes for game foreign_id={foreign_id}, skipping")

            else:
                game = Game()
                game.foreign_id = foreign_id
                game.home_team_id = home_team_id
                game.away_team_id = away_team_id
                game.home_team_goals = home_team_goals
                game.away_team_goals = away_team_goals
                game.status = status
                game.league_id = league_id
                game.stadium_id = 1
                game.date = parsed_date
                game.round = round_nr
                db.session.add(game)
                new_games.append(game_data)
                logger.info(f"New game added foreign_id={foreign_id}")

        db.session.commit()

        return {
            'total_scraped': len(scraped_games),
            'updated': updated_count,
            'new_pending': len(new_games)
        }

    # =========================
    # Helper Methods
    # =========================

    def get_pending_teams(self):
        """Get list of scraped teams pending completion"""
        return session.get(self.SCRAPED_GAMES_SESSION_KEY, [])

    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about teams"""
        total_teams = Team.query.count()
        pending_teams = len(self.get_pending_teams())

        return {
            'total_teams': total_teams,
            'pending_teams': pending_teams
        }
