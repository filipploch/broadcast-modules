from core.extensions import db
from core.models.base_league_scraper_url import BaseLeagueScraperUrlMixin


class LeagueScraperUrl(BaseLeagueScraperUrlMixin, db.Model):
    __tablename__ = 'league_scraper_urls'
