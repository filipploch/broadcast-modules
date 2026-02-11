"""Match Manager - CRUD operations for games (games)"""
from app.extensions import db
from app.models.game import Game
from app.models.league import League
from app.models.team import Team
from app.models.stadium import Stadium
from datetime import datetime
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)


class GameManager:
    """Manages CRUD operations for games (games)"""

    def get_all_games(self, league_id=None, team_id=None, status=None):
        """
        Get all games with optional filters

        Args:
            league_id: Filter by league ID (optional)
            team_id: Filter by team ID (home or away) (optional)
            status: Filter by status (optional)

        Returns:
            List of Game objects
        """
        query = Game.query

        if league_id:
            query = query.filter_by(league_id=league_id)

        if team_id:
            query = query.filter(
                (Game.home_team_id == team_id) | (Game.away_team_id == team_id)
            )

        if status is not None:
            query = query.filter_by(status=status)

        return query.order_by(Game.date.desc()).all()

    def get_game_by_id(self, game_id):
        """Get game by ID"""
        return Game.query.get(game_id)
    
    def get_game_by_foreign_id(self, foreign_id):
        return Game.query.get(foreign_id)

    def create_game(self, home_team_id, away_team_id, league_id, stadium_id,
                     round_number, group_nr=1, date=None, foreign_id=None):
        """
        Create new game

        Args:
            home_team_id: Home team ID
            away_team_id: Away team ID
            league_id: League ID
            stadium_id: Stadium ID
            round_number: Round number
            group_nr: Group number (default: 1)
            date: Match date (optional, datetime object)

        Returns:
            Game object or None if error

        Raises:
            ValueError if validation fails
        """
        # Validate teams exist and are different
        home_team = Team.query.get(home_team_id)
        if not home_team:
            raise ValueError(f"Nie znaleziono gospodarza o ID {home_team_id}")

        away_team = Team.query.get(away_team_id)
        if not away_team:
            raise ValueError(f"Nie znaleziono gościa o ID {away_team_id}")

        if home_team_id == away_team_id:
            raise ValueError("Gospodarz i gość nie mogą być tą samą drużyną")

        # Validate league exists
        league = League.query.get(league_id)
        if not league:
            raise ValueError(f"Nie znaleziono ligi o ID {league_id}")

        # Validate stadium exists
        stadium = Stadium.query.get(stadium_id)
        if not stadium:
            raise ValueError(f"Nie znaleziono stadionu o ID {stadium_id}")

        try:
            game = Game(
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                league_id=league_id,
                stadium_id=stadium_id,
                round=round_number,
                group_nr=group_nr,
                date=date,
                status=Game.STATUS_NOT_STARTED,
                foreign_id=foreign_id
            )
            db.session.add(game)
            db.session.commit()

            logger.info(f"Created game: {game}")
            return game

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating game: {e}")
            return None

    def update_game(self, game_id, home_team_id=None, away_team_id=None,
                    home_team_goals=None, away_team_goals=None,
                    is_home_team_lost_by_wo=None, is_away_team_lost_by_wo=None,
                     stadium_id=None, date=None, round_number=None, group_nr=None,
                     foreign_id=None):
        """
        Update game details

        Args:
            game_id: Match ID
            home_team_id: New home team ID (optional)
            away_team_id: New away team ID (optional)
            stadium_id: New stadium ID (optional)
            date: New game date (optional)
            round_number: New round number (optional)
            group_nr: New group number (optional)

        Returns:
            Updated Game object or None if error

        Raises:
            ValueError if game not found or validation fails
        """
        game = self.get_game_by_id(game_id)
        if not game:
            raise ValueError(f"Nie znaleziono meczu o ID {game_id}")

        try:
            # Update home team if provided
            print('-----------------------------------------------')
            print(f'is_home_team_lost_by_wo: {is_home_team_lost_by_wo}, type{type(is_home_team_lost_by_wo)}')
            print('-----------------------------------------------')
            if home_team_id is not None and home_team_id != game.home_team_id:
                home_team = Team.query.get(home_team_id)
                if not home_team:
                    raise ValueError(f"Nie znaleziono gospodarza o ID {home_team_id}")
                if home_team_id == game.away_team_id:
                    raise ValueError("Gospodarz i gość nie mogą być tą samą drużyną")
                game.home_team_id = home_team_id

            # Update away team if provided
            if away_team_id is not None and away_team_id != game.away_team_id:
                away_team = Team.query.get(away_team_id)
                if not away_team:
                    raise ValueError(f"Nie znaleziono gościa o ID {away_team_id}")
                if away_team_id == game.home_team_id:
                    raise ValueError("Gospodarz i gość nie mogą być tą samą drużyną")
                game.away_team_id = away_team_id
            if home_team_goals != game.home_team_goals:
                game.home_team_goals = home_team_goals
            if away_team_goals != game.away_team_goals:
                game.away_team_goals = away_team_goals
            game.is_home_team_lost_by_wo = 0
            if is_home_team_lost_by_wo is not None:
                game.is_home_team_lost_by_wo = 1
            game.is_away_team_lost_by_wo = 0
            if is_away_team_lost_by_wo is not None:
                game.is_away_team_lost_by_wo = 1

            # Update stadium if provided
            if stadium_id is not None and stadium_id != game.stadium_id:
                stadium = Stadium.query.get(stadium_id)
                if not stadium:
                    raise ValueError(f"Nie znaleziono stadionu o ID {stadium_id}")
                game.stadium_id = stadium_id

            # Update other fields if provided
            if date is not None:
                game.date = date
            if round_number is not None:
                game.round = round_number
            if group_nr is not None:
                game.group_nr = group_nr
            if foreign_id is not None:
                game.foreign_id = foreign_id

            db.session.commit()
            logger.info(f"Updated game: {game}")
            return game

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating game: {e}")
            return None

    def update_game_score(self, game_id, home_goals, away_goals,
                           home_fouls=None, away_fouls=None):
        """
        Update game score

        Args:
            game_id: Match ID
            home_goals: Home team goals
            away_goals: Away team goals
            home_fouls: Home team fouls (optional)
            away_fouls: Away team fouls (optional)

        Returns:
            Updated Game object or None if error

        Raises:
            ValueError if game not found
        """
        game = self.get_game_by_id(game_id)
        if not game:
            raise ValueError(f"Nie znaleziono meczu o ID {game_id}")

        try:
            game.update_score(home_goals, away_goals)

            if home_fouls is not None and away_fouls is not None:
                game.update_fouls(home_fouls, away_fouls)

            db.session.commit()
            logger.info(f"Updated game score: {game} - {home_goals}:{away_goals}")
            return game

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating game score: {e}")
            return None

    def set_game_status(self, game_id, status):
        """
        Set game status

        Args:
            game_id: Match ID
            status: New status (0=not started, 1=live, 2=finished)

        Returns:
            Updated Game object or None if error

        Raises:
            ValueError if game not found or invalid status
        """
        game = self.get_game_by_id(game_id)
        if not game:
            raise ValueError(f"Nie znaleziono meczu o ID {game_id}")

        if status not in [Game.STATUS_NOT_STARTED, Game.STATUS_PENDING, Game.STATUS_FINISHED]:
            raise ValueError(f"Nieprawidłowy status: {status}")

        try:
            if status == Game.STATUS_PENDING:
                game.set_live()
            elif status == Game.STATUS_FINISHED:
                game.set_finished()
            else:
                game.status = status

            db.session.commit()
            logger.info(f"Updated game status: {game} - {game.get_status_text()}")
            return game

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating game status: {e}")
            return None

    def set_walkover(self, game_id, home_team_wo=False, away_team_wo=False):
        """
        Set walkover flags for a game

        Args:
            game_id: Match ID
            home_team_wo: True if home team lost by walkover
            away_team_wo: True if away team lost by walkover

        Returns:
            Updated Game object or None if error

        Raises:
            ValueError if game not found
        """
        game = self.get_game_by_id(game_id)
        if not game:
            raise ValueError(f"Nie znaleziono meczu o ID {game_id}")

        try:
            if home_team_wo and away_team_wo:
                game.set_double_walkover()
            elif home_team_wo:
                game.set_home_walkover_loss()
            elif away_team_wo:
                game.set_away_walkover_loss()
            else:
                game.clear_walkovers()

            db.session.commit()
            logger.info(f"Updated game walkover status: {game}")
            return game

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error setting walkover: {e}")
            return None

    def delete_game(self, game_id):
        """
        Delete game

        Args:
            game_id: Match ID

        Returns:
            True if deleted, False if error

        Raises:
            ValueError if game not found
        """
        game = self.get_game_by_id(game_id)
        if not game:
            raise ValueError(f"Nie znaleziono meczu o ID {game_id}")

        try:
            db.session.delete(game)
            db.session.commit()

            logger.info(f"Deleted game {game_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting game: {e}")
            return False

    def get_upcoming_games(self, league_id=None, limit=10):
        """
        Get upcoming games (not started)

        Args:
            league_id: Filter by league ID (optional)
            limit: Maximum number of games to return

        Returns:
            List of Game objects
        """
        query = Game.query.filter_by(status=Game.STATUS_NOT_STARTED)

        if league_id:
            query = query.filter_by(league_id=league_id)

        return query.order_by(Game.date).limit(limit).all()

    def get_live_games(self, league_id=None):
        """
        Get live games (currently in progress)

        Args:
            league_id: Filter by league ID (optional)

        Returns:
            List of Game objects
        """
        query = Game.query.filter_by(status=Game.STATUS_PENDING)

        if league_id:
            query = query.filter_by(league_id=league_id)

        return query.order_by(Game.date).all()

    def get_finished_games(self, league_id=None, limit=10):
        """
        Get finished games

        Args:
            league_id: Filter by league ID (optional)
            limit: Maximum number of games to return

        Returns:
            List of Game objects
        """
        query = Game.query.filter_by(status=Game.STATUS_FINISHED)

        if league_id:
            query = query.filter_by(league_id=league_id)

        return query.order_by(Game.date.desc()).limit(limit).all()

    def get_games_by_round(self, league_id, round_number, group_nr=1):
        """
        Get all games in a specific round

        Args:
            league_id: League ID
            round_number: Round number
            group_nr: Group number (default: 1)

        Returns:
            List of Game objects
        """
        return Game.query.filter_by(
            league_id=league_id,
            round=round_number,
            group_nr=group_nr
        ).order_by(Game.date).all()

    def get_team_games(self, team_id, league_id=None, status=None):
        """
        Get all games for a specific team

        Args:
            team_id: Team ID
            league_id: Filter by league ID (optional)
            status: Filter by status (optional)

        Returns:
            List of Game objects
        """
        query = Game.query.filter(
            (Game.home_team_id == team_id) | (Game.away_team_id == team_id)
        )

        if league_id:
            query = query.filter_by(league_id=league_id)

        if status is not None:
            query = query.filter_by(status=status)

        return query.order_by(Game.date).all()

    def get_head_to_head(self, team1_id, team2_id, league_id=None):
        """
        Get head-to-head games between two teams

        Args:
            team1_id: First team ID
            team2_id: Second team ID
            league_id: Filter by league ID (optional)

        Returns:
            List of Game objects
        """
        query = Game.query.filter(
            ((Game.home_team_id == team1_id) & (Game.away_team_id == team2_id)) |
            ((Game.home_team_id == team2_id) & (Game.away_team_id == team1_id))
        )

        if league_id:
            query = query.filter_by(league_id=league_id)

        return query.order_by(Game.date.desc()).all()
