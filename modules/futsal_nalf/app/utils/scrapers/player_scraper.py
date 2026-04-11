"""PlayerScraper - scraping players data from nalffutsal.pl team pages"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PlayerScraper:
    """Scraper for NALF Futsal player data from team pages"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def scrape_players(self, team_url: str) -> List[Dict]:
        """
        Scrape players from a team page.

        Args:
            team_url: Full URL to the team page (e.g. https://nalffutsal.pl/?sp_team=zarlacze)

        Returns:
            List of player dictionaries
        """
        try:
            response = self.session.get(team_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            table = soup.find('table')
            if not table:
                logger.warning(f"No player table found on page {team_url}")
                return []

            tbody = table.find('tbody')
            if not tbody:
                logger.warning(f"No tbody in player table on {team_url}")
                return []

            players = []
            for row in tbody.find_all('tr'):
                player_data = self._extract_player_from_row(row)
                if player_data:
                    players.append(player_data)

            logger.info(f"Scraped {len(players)} players from {team_url}")
            return players

        except requests.RequestException as e:
            logger.error(f"Error scraping {team_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error scraping {team_url}: {e}")
            return []

    def _extract_player_from_row(self, row) -> Optional[Dict]:
        """Extract player data from a table row."""
        try:
            name_cell = row.find('td', class_='data-name')
            if not name_cell:
                return None

            name_link = name_cell.find('a')
            if not name_link:
                return None

            href = name_link.get('href', '')
            if 'sp_player=' not in href:
                return None

            foreign_id = href.split('sp_player=')[1]

            # "Antoszewski Marcin" → last_name="Antoszewski", first_name="Marcin"
            name_parts = name_link.get_text(strip=True).split()
            if len(name_parts) < 2:
                return None
            first_name = name_parts[-1]
            last_name = ' '.join(name_parts[:-1])

            position_cell = row.find('td', class_='data-position')
            position_text = position_cell.get_text(strip=True) if position_cell else ''
            is_goalkeeper = (position_text == 'Bramkarz')

            # Extract team foreign_id from data-team cell
            team_cell = row.find('td', class_='data-team')
            team_foreign_id = None
            if team_cell:
                team_link = team_cell.find('a')
                if team_link:
                    team_href = team_link.get('href', '')
                    if 'sp_team=' in team_href:
                        team_foreign_id = team_href.split('sp_team=')[1]

            return {
                'foreign_id': foreign_id,
                'first_name': first_name,
                'last_name': last_name,
                'is_goalkeeper': is_goalkeeper,
                'team_foreign_id': team_foreign_id,
            }

        except Exception as e:
            logger.error(f"Error extracting player from row: {e}")
            return None
