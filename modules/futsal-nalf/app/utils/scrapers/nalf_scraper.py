"""NALF Futsal Scraper - scraping team data from nalffutsal.pl"""
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class NALFScraper:
    """Scraper for NALF Futsal league tables"""
    
    BASE_URL = "https://nalffutsal.pl"
    
    def __init__(self):
        # self._stop_event = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    # def set_stop_event(self, stop_event):
        # """Set the stop event for cooperative stopping"""
        # self._stop_event = stop_event

    # def stop_scraping(self):
        # """Stop scraping immediately"""
        # # Tutaj możesz dodać kod do zatrzymania aktywnych operacji
        # # np. zamknąć sesję requests, przerwać pętle, etc.
        # if hasattr(self, 'session'):
            # self.session.close()
    
    def scrape_league_table(self, page_url: str) -> List[Dict[str, str]]:
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
            teams = []
            
            # Find table body
            # tbodies = soup.find_all('tbody')

            tbody = soup.find('tbody')
            if not tbody:
                logger.warning(f"No tbody found on page {page_url}")
                return teams

            print(tbody)
            
            # Find all team rows
            rows = tbody.find_all('tr')
            
            for row in rows:
                print(f"<tr>: {row}")
                team_data = self._extract_team_from_row(row)
                print(f"    team_data: {team_data}")
                if team_data:
                    teams.append(team_data)
            
            logger.info(f"Scraped {len(teams)} teams from {page_url}")
            return teams
            
        except requests.RequestException as e:
            logger.error(f"Error scraping {page_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error scraping {page_url}: {e}")
            return []
    
    def _extract_team_from_row(self, row) -> Optional[Dict[str, str]]:
        """
        Extract team data from a table row
        
        Args:
            row: BeautifulSoup row element
        
        Returns:
            Dictionary with 'name' and 'team_url' or None if extraction fails
        """
        try:
            # Find the team name cell
            name_cell = row.find('td', class_='data-name')
            if not name_cell:
                return None
            
            # Find the link with team info
            link = name_cell.find('a')
            if not link:
                return None
            
            team_url = link.get('href', '').strip()
            team_name = link.get_text(strip=True)
            
            if not team_url or not team_name:
                return None
            
            # Ensure absolute URL
            if not team_url.startswith('http'):
                team_url = self.BASE_URL + team_url
            
            return {
                'name': team_name,
                'team_url': team_url
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
        all_teams = []
        seen_urls = set()
        
        for url in page_urls:
            teams = self.scrape_league_table(url)
            
            # Add only unique teams (by team_url)
            for team in teams:
                if team['team_url'] not in seen_urls:
                    all_teams.append(team)
                    seen_urls.add(team['team_url'])
        
        logger.info(f"Scraped {len(all_teams)} unique teams from {len(page_urls)} pages")
        return all_teams
