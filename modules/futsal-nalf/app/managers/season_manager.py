"""Season Manager - CRUD operations for seasons"""
from app.extensions import db
from app.models.season import Season
from app.models.league import League
from app.models.game import Game
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)


class SeasonManager:
    """Manages CRUD operations for seasons"""

    def get_all_seasons(self):
        """Get all seasons ordered by number (newest first)"""
        return Season.query.order_by(Season.number.desc()).all()

    def get_season_by_id(self, season_id):
        """Get season by ID"""
        return Season.query.get(season_id)

    def get_season_by_number(self, number):
        """Get season by number"""
        return Season.query.filter_by(number=number).first()

    def create_season(self, number, name, foreign_id=None):
        """
        Create new season

        Args:
            number: Season number (must be unique)
            name: Season name (e.g., "Jesień 2025")
            foreign_id: Optional external ID for integration

        Returns:
            Season object or None if error

        Raises:
            ValueError if season with this number or name already exists
        """
        # Check if season with this number already exists
        existing_number = self.get_season_by_number(number)
        if existing_number:
            raise ValueError(f"Sezon o numerze {number} już istnieje")

        # Check if season with this name already exists
        existing_name = Season.query.filter_by(name=name).first()
        if existing_name:
            raise ValueError(f"Sezon o nazwie '{name}' już istnieje")

        try:
            season = Season(
                number=number,
                name=name,
                foreign_id=foreign_id
            )
            db.session.add(season)
            db.session.commit()

            logger.info(f"Created season: {season}")
            return season

        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"IntegrityError creating season: {e}")
            raise ValueError("Nie można utworzyć sezonu - naruszenie unikalności danych")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating season: {e}")
            return None

    def update_season(self, season_id, number=None, name=None, foreign_id=None):
        """
        Update season

        Args:
            season_id: Season ID
            number: New season number (optional)
            name: New season name (optional)
            foreign_id: New foreign ID (optional)

        Returns:
            Updated Season object or None if error

        Raises:
            ValueError if season not found or duplicate data
        """
        season = self.get_season_by_id(season_id)
        if not season:
            raise ValueError(f"Nie znaleziono sezonu o ID {season_id}")

        try:
            # Update number if provided
            if number is not None and number != season.number:
                # Check if new number is unique
                existing = Season.query.filter(
                    Season.number == number,
                    Season.id != season_id
                ).first()
                if existing:
                    raise ValueError(f"Sezon o numerze {number} już istnieje")
                season.number = number

            # Update name if provided
            if name is not None and name != season.name:
                # Check if new name is unique
                existing = Season.query.filter(
                    Season.name == name,
                    Season.id != season_id
                ).first()
                if existing:
                    raise ValueError(f"Sezon o nazwie '{name}' już istnieje")
                season.name = name

            # Update foreign_id if provided
            if foreign_id is not None:
                season.foreign_id = foreign_id

            db.session.commit()
            logger.info(f"Updated season: {season}")
            return season

        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"IntegrityError updating season: {e}")
            raise ValueError("Nie można zaktualizować sezonu - naruszenie unikalności danych")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating season: {e}")
            return None

    def delete_season(self, season_id):
        """
        Delete season (will cascade delete all leagues and games in this season)

        Args:
            season_id: Season ID

        Returns:
            True if deleted, False if error

        Raises:
            ValueError if season not found
        """
        season = self.get_season_by_id(season_id)
        if not season:
            raise ValueError(f"Nie znaleziono sezonu o ID {season_id}")

        try:
            # Get stats before deletion for logging
            leagues_count = season.total_leagues
            games_count = season.total_games

            db.session.delete(season)
            db.session.commit()

            logger.info(f"Deleted season {season_id}: {season.name} "
                        f"(with {leagues_count} leagues and {games_count} games)")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting season: {e}")
            return False

    def get_season_statistics(self, season_id):
        """
        Get detailed statistics for a season

        Args:
            season_id: Season ID

        Returns:
            Dictionary with season statistics or None if season not found
        """
        season = self.get_season_by_id(season_id)
        if not season:
            return None

        leagues = season.leagues.all()
        total_games = season.total_games
        finished_games = Game.query.join(League).filter(
            League.season_id == season_id,
            Game.status == Game.STATUS_FINISHED
        ).count()
        live_games = Game.query.join(League).filter(
            League.season_id == season_id,
            Game.status == Game.STATUS_PENDING
        ).count()
        upcoming_games = Game.query.join(League).filter(
            League.season_id == season_id,
            Game.status == Game.STATUS_NOT_STARTED
        ).count()

        # Get unique teams playing in this season
        from app.models.league_team import LeagueTeam
        teams_count = db.session.query(LeagueTeam.team_id).join(League).filter(
            League.season_id == season_id
        ).distinct().count()

        return {
            'season': season.to_dict(),
            'leagues': [league.to_dict() for league in leagues],
            'total_leagues': len(leagues),
            'total_teams': teams_count,
            'total_games': total_games,
            'finished_games': finished_games,
            'live_games': live_games,
            'upcoming_games': upcoming_games
        }

    def get_current_season(self):
        """
        Get the latest (current) season based on highest season number

        Returns:
            Season object or None if no seasons exist
        """
        return Season.query.order_by(Season.number.desc()).first()

    def set_as_current(self, season_id):
        """
        Helper method to conceptually mark a season as "current"
        (In this implementation, "current" is simply the one with highest number,
        but this method could be extended to use a flag in the future)

        Args:
            season_id: Season ID

        Returns:
            Season object
        """
        return self.get_season_by_id(season_id)
