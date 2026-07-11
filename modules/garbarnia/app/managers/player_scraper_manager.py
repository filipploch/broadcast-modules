"""Player Scraper Manager - scraping and syncing players for a team"""
from typing import Dict, List, Optional
from flask import current_app
from core.extensions import db
from app.models.player import Player
from app.models.team import Team
from core.managers.player_manager import PlayerManager
import threading
import logging
import sys

logger = logging.getLogger(__name__)

player_manager = PlayerManager()


class PlayerScraperManager:
    """Manager for scraping and syncing players from NALF team pages"""

    def __init__(self):
        self._scraping_thread = None
        self._scraping_lock = threading.Lock()
        self._status: Dict = {
            'status': 'idle',
            'team_name': None,
            'added': 0,
            'updated': 0,
            'error': None,
        }

    def check_file_exists(self, team_id: int) -> bool:
        """Sprawdza czy plik HTML dla drużyny istnieje w katalogu temp."""
        team = Team.query.get(team_id)
        if not team or not team.foreign_id:
            return False
        temp_dir = sys.path[0] + current_app.config['TEMP_DIR']
        from app.managers.scrapers.laczynaspilka import PlayerScraper
        return PlayerScraper().find_html_file_for_team(temp_dir, team.foreign_id) is not None

    # =========================
    # Scraping Workflow (Threaded)
    # =========================

    def scrape_players_async(self, team_id: int) -> bool:
        """
        Start scraping players for a team in a background thread.

        Args:
            team_id: Team ID (used to fetch team_url and team.foreign_id)

        Returns:
            True if scraping started, False if already running or team invalid
        """
        team = Team.query.get(team_id)
        if not team:
            logger.error(f"Team ID {team_id} not found")
            return False
        if not team.foreign_id:
            logger.error(f"Team {team.name} has no foreign_id configured")
            return False

        with self._scraping_lock:
            if self._scraping_thread and self._scraping_thread.is_alive():
                logger.warning("Player scraping already in progress")
                return False

            self._status = {
                'status': 'in_progress',
                'team_name': team.name,
                'added': 0,
                'updated': 0,
                'error': None,
            }

            app = current_app._get_current_object()

            from core.extensions import socketio
            socketio.emit('scraping_started', {'name': team.name})

            self._scraping_thread = threading.Thread(
                target=self._scrape_worker,
                args=(app, team_id),
                daemon=True
            )
            self._scraping_thread.start()

            logger.info(f"Started player scraping for team {team.name}")
            return True

    def _scrape_worker(self, app, team_id: int):
        """Background worker — runs in a separate thread."""
        with app.app_context():
            from core.extensions import socketio
            team = Team.query.get(team_id)
            temp_dir = sys.path[0] + app.config['TEMP_DIR']
            try:
                from app.managers.scrapers.laczynaspilka import PlayerScraper

                scraper = PlayerScraper()
                scraped_players = scraper.scrape_players(temp_dir, team.foreign_id)
                stats = self._process_scraped_players(scraped_players, team)
                html_path = scraper.find_html_file_for_team(temp_dir, team.foreign_id)
                if html_path and html_path.exists():
                    html_path.unlink()
                    logger.info(f"Usunięto plik HTML po scrapowaniu: {html_path.name}")

                self._status = {
                    'status': 'completed',
                    'team_name': team.name,
                    'added': stats['added'],
                    'updated': stats['updated'],
                    'error': None,
                }

                logger.info(
                    f"Player scraping completed for {team.name}: "
                    f"{stats['added']} added, {stats['updated']} updated"
                )

                socketio.emit('scraping_completed', {
                    'name': team.name,
                    'team_id': team.id,
                    'added': stats['added'],
                    'updated': stats['updated'],
                })
                socketio.emit('player_scraping_completed', {
                    'team_id': team.id,
                })

            except Exception as e:
                logger.error(f"Player scraping error for team {team_id}: {e}", exc_info=True)
                self._status = {
                    'status': 'error',
                    'team_name': team.name if team else None,
                    'added': 0,
                    'updated': 0,
                    'error': str(e),
                }
                socketio.emit('scraping_error', {
                    'name': team.name if team else '',
                    'error': str(e),
                })

    # =========================
    # Processing
    # =========================

    def _process_scraped_players(self, scraped_players: List[Dict], team: Team) -> Dict[str, int]:
        """
        Sync scraped players with the database for a given team.

        Rules:
        - Match by foreign_id (primary key for scraped players)
        - If found by foreign_id: update first_name, last_name, is_goalkeeper if changed
        - If not found by foreign_id: insert as new player
        - Players in DB with a foreign_id that are NOT in the scraped list
          are considered to have left the team — their team_id is set to None
          (preserves historical data, just detaches from the team)
        - Players without a foreign_id (manually added) are left untouched

        Args:
            scraped_players: List of player dicts from PlayerScraper
            team: Team ORM object

        Returns:
            {'added': int, 'updated': int}
        """
        added = 0
        updated = 0

        scraped_foreign_ids = {p['foreign_id'] for p in scraped_players}

        for player_data in scraped_players:
            foreign_id = player_data['foreign_id']
            existing = player_manager.get_player_by_foreign_id(foreign_id)

            if existing:
                changes = {}
                if existing.first_name != player_data['first_name']:
                    changes['first_name'] = player_data['first_name']
                if existing.last_name != player_data['last_name']:
                    changes['last_name'] = player_data['last_name']
                if existing.is_goalkeeper != player_data['is_goalkeeper']:
                    changes['is_goalkeeper'] = player_data['is_goalkeeper']
                if existing.number != player_data['number']:
                    changes['number'] = player_data['number']
                # Always sync team_id — player may have transferred back
                if existing.team_id != team.id:
                    changes['team_id'] = team.id

                if changes:
                    for field, value in changes.items():
                        setattr(existing, field, value)
                    logger.info(f"Updated player foreign_id={foreign_id}, changed: {list(changes.keys())}")
                    updated += 1
                else:
                    logger.debug(f"No changes for player foreign_id={foreign_id}")
            else:
                new_player = Player(
                    foreign_id=foreign_id,
                    first_name=player_data['first_name'],
                    last_name=player_data['last_name'],
                    team_id=team.id,
                    is_goalkeeper=player_data['is_goalkeeper'],
                    is_captain=False,
                    number=player_data['number'],
                )
                db.session.add(new_player)
                logger.info(f"Added player {player_data['first_name']} {player_data['last_name']} to {team.name}")
                added += 1

        # Detach players who are no longer on this team's scraped roster
        # Only applies to players WITH a foreign_id (scraped), not manually added ones
        departed = Player.query.filter(
            Player.team_id == team.id,
            Player.foreign_id.isnot(None),
            Player.foreign_id.notin_(scraped_foreign_ids)
        ).all()

        for player in departed:
            player.team_id = None
            logger.info(
                f"Player {player.full_name} (foreign_id={player.foreign_id}) "
                f"no longer in {team.name} roster — detached from team"
            )

        db.session.commit()

        return {'added': added, 'updated': updated}

    # =========================
    # Status
    # =========================

    def get_scraping_status(self) -> Dict:
        """Get current scraping status."""
        return self._status.copy()

    def is_scraping_in_progress(self) -> bool:
        """Check if scraping is currently running"""
        return self._status['status'] == 'in_progress'

    def clear_scraping_status(self):
        """Reset status to idle"""
        self._status = {
            'status': 'idle',
            'team_name': None,
            'added': 0,
            'updated': 0,
            'error': None,
        }
