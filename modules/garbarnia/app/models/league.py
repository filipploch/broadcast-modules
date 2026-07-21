"""League — moduł garbarnia.

Rozszerza BaseLeagueMixin o parametry scraperów specyficzne dla ligi, które nie
pasują do generycznego kształtu LeagueScraperUrl (URL-e per scraper są tam).
"""
from core.extensions import db
from core.models.base_league import BaseLeagueMixin


class League(BaseLeagueMixin, db.Model):
    __tablename__ = 'leagues'

    superscore_season_id  = db.Column(db.String(100), nullable=True)
    # UUID used as ?playDictionary= query param on laczynaspilka.pl team pages
    # (= ?group= query param on the /rozgrywki league listing page)
    play_dictionary_id    = db.Column(db.String(100), nullable=True)
    # UUID used as ?season= query param on laczynaspilka.pl (/rozgrywki listing
    # and team pages) — the season the league's play_dictionary_id belongs to.
    laczynaspilka_season_id = db.Column(db.String(100), nullable=True)
