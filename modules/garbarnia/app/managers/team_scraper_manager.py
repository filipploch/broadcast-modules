"""Team Scraper Manager - statistics helper for the team list page.

The old scrape-team-list-from-web workflow (scrape_leagues_async / pending
teams / complete_team_from_scraping) was never wired to a route in either
module and has been removed. Team-list scraping will be reimplemented
differently.
"""
from typing import Dict
from app.models.team import Team


class TeamScraperManager:
    """Provides team statistics for the team list page."""

    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about teams"""
        return {'total_teams': Team.query.count()}
