"""NALF Futsal Scraper - scraping games data from nalffutsal.pl"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class GameScraper:
    """Scraper for NALF Futsal league tables"""
    
    BASE_URL = "https://nalffutsal.pl"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    
    def scrape_game(self, page_url: str) -> List[Dict[str, str]]:
        """
        Scrape teams from a league table page
        
        Args:
            page_url: Full URL to the league table page (e.g., https://nalffutsal.pl/?page_id=16)
        
        Returns:
            List of dictionaries with team data: {'name': str, 'team_url': str}
        """
        try:
            response = self.session.get(page_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            games = []
            
            # Find table body

            tbody = soup.find('tbody')
            if not tbody:
                logger.warning(f"No tbody found on page {page_url}")
                return games

            print(tbody)
            
            # Find all team rows
            rows = tbody.find_all('tr')
            
            for row in rows:
                print(f"<tr>: {row}")
                game_data = self._extract_game_data_from_row(row)
                print(f"    game_data: {game_data}")
                if game_data:
                    games.append(game_data)
            
            logger.info(f"Scraped {len(games)} teams from {page_url}")
            return games
            
        except requests.RequestException as e:
            logger.error(f"Error scraping {page_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error scraping {page_url}: {e}")
            return []
    
    def _extract_game_data_from_row(self, row) -> Optional[Dict[str, str]]:
        """
        Extract game data from a table row
        
        Args:
            row: BeautifulSoup row element
        
        Returns:
            Dictionary with 'name' and 'team_url' or None if extraction fails
        """
        try:
            # Find the team name cell
            date_cell = row.find('td', class_='data-date')
            if not date_cell:
                return None
            
            date = date_cell.get('content')
            
            game_cell = row.find('td', class_='data-event')
            if not game_cell:
                return None
            
            # Find the link with team info
            link = game_cell.find('a')
            if not link:
                return None
            
            foreign_id = link.get('href', '').strip().split('sp_event=')[1]
            teams_names = link.get_text(strip=True).split(' — ')
            home_team_name = teams_names[0].strip()
            away_team_name = teams_names[1].strip()
            
            if not foreign_id or not home_team_name or not away_team_name:
                return None
            
            result_cell = row.find('td', class_='data-time')
            if not result_cell:
                return None
            
            result = result_cell.find('a').get_text(strip=True)
            if not result:
                return None
            
            if ' - ' in result:
                status = 2
                home_team_goals = int(result.split(' - ')[0])
                away_team_goals = int(result.split(' - ')[1])
            else:
                status = 0
                home_team_goals = None
                away_team_goals = None
            
            if not status or not home_team_goals or not away_team_goals:
                return None
            
            league_txt = row.find('td', class_='data-league').get_text(strip=True)
            if not league_txt:
                return None
            
            league_dict = {
                'Dywizja A': 1,
                'Dywizja B': 2,
                'Puchar Ligi': 3
            }

            league_id = league_dict[league_txt]
            if not league_id:
                return None
            
            round_txt = row.find('td', class_='data-day').get_text(strip=True)
            if not round_txt:
                return None
            
            round = 0

            cup_rounds = {
                '1/16 finału': 1,
                '1/8 finału': 2,
                'Ćwierćfinał': 3,
                'Półfinał': 4,
                'Mecz o 3. miejsce': 5,
                'Finał': 6
            }

            if round_txt.isdigit():
                round = int(round_txt)
            else:
                round = cup_rounds[round_txt]
            return {
                'foreign_id': foreign_id,
                'home_team_name': home_team_name,
                'away_team_name': away_team_name,
                'home_team_goals': home_team_goals,
                'away_team_goals': away_team_goals,
                'status': status,
                'league_id': league_id,
                'date': date,
                'round': round
            }
            
        except Exception as e:
            logger.error(f"Error extracting team from row: {e}")
            return None
    
    def scrape_multiple_leagues(self, page_urls: List[str]) -> List[Dict[str, str]]:
        """
        Scrape teams from multiple league table pages
        
        Args:
            page_urls: List of full URLs to league table pages
        
        Returns:
            List of unique teams (deduplicated by team_url)
        """
        all_games = []
        
        for url in page_urls:
            games = self.scrape_game(url)
            
            # Add only unique teams (by team_url)
            for game in games:
                all_games.append(game)
        
        return all_games
