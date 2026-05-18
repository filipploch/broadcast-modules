"""League Manager - CRUD operations for leagues"""
from core.extensions import db

# from core.models.base_season import Season
# from core.models.base_league_team import LeagueTeam

from sqlalchemy.exc import IntegrityError
import logging

def _get_league():
    from core.models.base_league import get_league_model
    return get_league_model()

def _get_season():
    from core.models.base_season import get_season_model
    return get_season_model()

def _get_league_team():
    from core.models.base_league_team import get_league_team_model
    return get_league_team_model()

def _get_team():
    from core.models.base_team import get_team_model
    return get_team_model()

def _get_game():
    from core.models.base_game import get_game_model
    return get_game_model()

logger = logging.getLogger(__name__)


class LeagueManager:
    """Manages CRUD operations for leagues"""

    def get_all_leagues(self, season_id=None):
        """
        Get all leagues, optionally filtered by season

        Args:
            season_id: Optional season ID to filter by

        Returns:
            List of League objects
        """
        League = _get_league()
        query = League.query
        if season_id:
            query = query.filter_by(season_id=season_id)
        return query.order_by(League.season_id.desc(), League.name).all()

    def get_league_by_id(self, league_id):
        """Get league by ID"""
        League = _get_league()
        return League.query.get(league_id)

    def create_league(self, season_id, name, games_url=None, scorers_url=None,
                      assists_url=None, canadian_url=None, table_url=None,
                      foreign_id=None, allows_draw=True):
        """
        Create new league

        Args:
            season_id: Season ID
            name: League name (e.g., "Dywizja A", "Puchar Ligi")
            games_url: URL to games table
            scorers_url: URL to scorers table
            assists_url: URL to assists table
            canadian_url: URL to canadian points table
            table_url: Optional URL to league table
            allows_draw: True = liga grupowa (remis dozwolony),
                         False = rozgrywki pucharowe (remis → rzuty karne)

        Returns:
            League object or None if error

        Raises:
            ValueError if validation fails
        """
        League = _get_league()
        Season = _get_season()
        # Validate season exists
        season = Season.query.get(season_id)
        if not season:
            raise ValueError(f"Nie znaleziono sezonu o ID {season_id}")

        # Check if league with this name already exists in this season
        existing = League.query.filter_by(season_id=season_id, name=name).first()
        if existing:
            raise ValueError(f"Liga '{name}' już istnieje w sezonie {season.name}")

        try:
            kwargs = dict(season_id=season_id, name=name, allows_draw=allows_draw,
                          foreign_id=foreign_id)
            for field, val in (('games_url', games_url), ('table_url', table_url),
                               ('scorers_url', scorers_url), ('assists_url', assists_url),
                               ('canadian_url', canadian_url)):
                if hasattr(League, field):
                    kwargs[field] = val
            league = League(**kwargs)
            db.session.add(league)
            db.session.commit()

            logger.info(f"Created league: {league}")
            return league

        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"IntegrityError creating league: {e}")
            raise ValueError("Nie można utworzyć ligi - naruszenie unikalności danych")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating league: {e}")
            return None

    def update_league(self, league_id, name=None, games_url=None, table_url=None,
                      scorers_url=None, assists_url=None, canadian_url=None,
                      foreign_id=None, allows_draw=None):
        """
        Update league

        Args:
            league_id: League ID
            name: New league name (optional)
            games_url: New games URL (optional)
            table_url: New table URL (optional)
            scorers_url: New scorers URL (optional)
            assists_url: New assists URL (optional)
            canadian_url: New canadian URL (optional)

        Returns:
            Updated League object or None if error

        Raises:
            ValueError if league not found or validation fails
        """
        League = _get_league()
        league = self.get_league_by_id(league_id)
        if not league:
            raise ValueError(f"Nie znaleziono ligi o ID {league_id}")

        try:
            # Update name if provided
            if allows_draw is not None:
                league.allows_draw = allows_draw
            if name is not None and name != league.name:
                # Check if new name is unique within the season
                existing = League.query.filter(
                    League.season_id == league.season_id,
                    League.name == name,
                    League.id != league_id
                ).first()
                if existing:
                    raise ValueError(f"Liga o nazwie '{name}' już istnieje w tym sezonie")
                league.name = name

            # Update URLs if provided
            if games_url is not None:
                league.games_url = games_url
            if table_url is not None:
                league.table_url = table_url
            if scorers_url is not None:
                league.scorers_url = scorers_url
            if assists_url is not None:
                league.assists_url = assists_url
            if canadian_url is not None:
                league.canadian_url = canadian_url
            if foreign_id is not None:
                league.foreign_id = foreign_id

            db.session.commit()
            logger.info(f"Updated league: {league}")
            return league

        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"IntegrityError updating league: {e}")
            raise ValueError("Nie można zaktualizować ligi - naruszenie unikalności danych")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating league: {e}")
            return None

    def delete_league(self, league_id):
        """
        Delete league (will cascade delete all games and team associations)

        Args:
            league_id: League ID

        Returns:
            True if deleted, False if error

        Raises:
            ValueError if league not found
        """
        league = self.get_league_by_id(league_id)
        if not league:
            raise ValueError(f"Nie znaleziono ligi o ID {league_id}")

        try:
            # Get stats before deletion for logging
            teams_count = league.total_teams
            games_count = league.total_games

            db.session.delete(league)
            db.session.commit()

            logger.info(f"Deleted league {league_id}: {league.name} "
                        f"(with {teams_count} teams and {games_count} games)")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting league: {e}")
            return False

    def get_league_statistics(self, league_id):
        """
        Get detailed statistics for a league

        Args:
            league_id: League ID

        Returns:
            Dictionary with league statistics or None if league not found
        """
        Game = _get_game()
        LeagueTeam = _get_league_team()
        league = self.get_league_by_id(league_id)
        if not league:
            return None

        from core.models.base_game import get_game_model

        teams = league.get_teams()
        total_games = league.total_games
        finished_games = league.games.filter_by(status=Game.STATUS_FINISHED).count()
        live_games = league.games.filter_by(status=Game.STATUS_PENDING).count()
        upcoming_games = league.games.filter_by(status=Game.STATUS_NOT_STARTED).count()

        # Get groups
        groups = db.session.query(LeagueTeam.group_nr).filter_by(
            league_id=league_id
        ).distinct().order_by(LeagueTeam.group_nr).all()
        groups = [g[0] for g in groups]

        return {
            'league': league.to_dict(),
            'teams': [lt.to_dict() for lt in teams],
            'total_teams': len(teams),
            'groups': groups,
            'total_groups': len(groups),
            'total_games': total_games,
            'finished_games': finished_games,
            'live_games': live_games,
            'upcoming_games': upcoming_games
        }

    def add_team_to_league(self, league_id, team_id, group_nr=1):
        """
        Add team to league

        Args:
            league_id: League ID
            team_id: Team ID
            group_nr: Group number (default: 1)

        Returns:
            LeagueTeam object or None if error

        Raises:
            ValueError if league or team not found, or team already in league
        """
        Team = _get_team()
        LeagueTeam = _get_league_team()
        league = self.get_league_by_id(league_id)
        if not league:
            raise ValueError(f"Nie znaleziono ligi o ID {league_id}")

        team = Team.query.get(team_id)
        if not team:
            raise ValueError(f"Nie znaleziono zespołu o ID {team_id}")

        # Check if team already in this league
        existing = LeagueTeam.query.filter_by(
            league_id=league_id,
            team_id=team_id
        ).first()
        if existing:
            raise ValueError(f"Zespół {team.name} już jest w tej lidze")

        try:
            league_team = LeagueTeam(
                league_id=league_id,
                team_id=team_id,
                group_nr=group_nr
            )
            db.session.add(league_team)
            db.session.commit()

            logger.info(f"Added team {team.name} to league {league.name} (group {group_nr})")
            return league_team

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding team to league: {e}")
            return None

    def remove_team_from_league(self, league_id, team_id):
        """
        Remove team from league

        Args:
            league_id: League ID
            team_id: Team ID

        Returns:
            True if removed, False if error

        Raises:
            ValueError if association not found
        """
        LeagueTeam = _get_league_team()
        league_team = LeagueTeam.query.filter_by(
            league_id=league_id,
            team_id=team_id
        ).first()

        if not league_team:
            raise ValueError("Zespół nie jest przypisany do tej ligi")

        try:
            db.session.delete(league_team)
            db.session.commit()

            logger.info(f"Removed team {team_id} from league {league_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing team from league: {e}")
            return False

    def update_team_group(self, league_id, team_id, group_nr):
        """
        Update team's group number in a league

        Args:
            league_id: League ID
            team_id: Team ID
            group_nr: New group number

        Returns:
            Updated LeagueTeam object or None if error

        Raises:
            ValueError if association not found
        """
        LeagueTeam = _get_league_team()
        league_team = LeagueTeam.query.filter_by(
            league_id=league_id,
            team_id=team_id
        ).first()

        if not league_team:
            raise ValueError("Zespół nie jest przypisany do tej ligi")

        try:
            league_team.group_nr = group_nr
            db.session.commit()

            logger.info(f"Updated team {team_id} group to {group_nr} in league {league_id}")
            return league_team

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating team group: {e}")
            return None

    def get_league_teams(self, league_id, group_nr=None):
        """
        Get teams in a league, optionally filtered by group

        Args:
            league_id: League ID
            group_nr: Optional group number to filter by

        Returns:
            List of LeagueTeam objects
        """
        league = self.get_league_by_id(league_id)
        if not league:
            return []

        return league.get_teams(group_nr=group_nr)

    def get_available_teams(self, league_id):
        """
        Get teams that are not yet in this league

        Args:
            league_id: League ID

        Returns:
            List of Team objects not in this league
        """
        LeagueTeam = _get_league_team()
        Team = _get_team()
        # Get IDs of teams already in this league
        assigned_team_ids = db.session.query(LeagueTeam.team_id).filter_by(
            league_id=league_id
        ).all()
        assigned_team_ids = [t[0] for t in assigned_team_ids]

        # Get teams not in this league
        if assigned_team_ids:
            available_teams = Team.query.filter(
                ~Team.id.in_(assigned_team_ids)
            ).order_by(Team.name).all()
        else:
            available_teams = Team.query.order_by(Team.name).all()

        return available_teams
