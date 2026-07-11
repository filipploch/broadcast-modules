from core.extensions import db
from core.models.base_active_scraper_config import BaseActiveScraperConfigMixin


class ActiveScraperConfig(BaseActiveScraperConfigMixin, db.Model):
    __tablename__ = 'active_scraper_configs'
