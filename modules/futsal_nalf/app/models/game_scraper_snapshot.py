from core.extensions import db
from core.models.base_game_scraper_snapshot import BaseGameScraperSnapshotMixin


class GameScraperSnapshot(BaseGameScraperSnapshotMixin, db.Model):
    __tablename__ = 'game_scraper_snapshots'
