from core.extensions import db
from core.models.base_scraper import BaseScraperMixin


class Scraper(BaseScraperMixin, db.Model):
    __tablename__ = 'scrapers'
