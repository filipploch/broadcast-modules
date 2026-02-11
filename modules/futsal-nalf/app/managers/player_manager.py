"""Player Manager - handles CRUD operations for Player model"""
from typing import List, Optional
from app.extensions import db
from app.models.player import Player
from app.models.team import Team
import logging

logger = logging.getLogger(__name__)


class PlayerManager:
    """Manager for Player CRUD operations"""

    def create_player(self, first_name: str, last_name: str, team_id: int,
                     number: int = None, is_goalkeeper: bool = False,
                     is_captain: bool = False, foreign_id: str = None) -> Optional[Player]:
        """
        Create new player

        Args:
            first_name: Player first name
            last_name: Player last name
            team_id: Team ID
            number: Jersey number (optional)
            is_goalkeeper: Is goalkeeper (default: False)
            is_captain: Is captain (default: False)
            foreign_id: External ID (optional)

        Returns:
            Player object or None if error

        Raises:
            ValueError if team not found
        """
        # Validate team exists
        team = Team.query.get(team_id)
        if not team:
            raise ValueError(f"Zespół o ID {team_id} nie istnieje")

        try:
            player = Player(
                first_name=first_name,
                last_name=last_name,
                team_id=team_id,
                number=number,
                is_goalkeeper=is_goalkeeper,
                is_captain=is_captain,
                foreign_id=foreign_id
            )
            db.session.add(player)
            db.session.commit()

            logger.info(f"Created player: {player.full_name} (Team: {team.name})")
            return player

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating player: {e}")
            raise

    def get_all_players(self) -> List[Player]:
        """Get all players"""
        return Player.query.order_by(Player.last_name, Player.first_name).all()

    def get_players_by_team(self, team_id: int) -> List[Player]:
        """Get all players for a specific team"""
        return Player.query.filter_by(team_id=team_id).order_by(
            Player.number.asc().nullslast(),
            Player.last_name,
            Player.first_name
        ).all()

    def get_player_by_id(self, player_id: int) -> Optional[Player]:
        """Get player by ID"""
        return Player.query.get(player_id)

    def get_player_by_foreign_id(self, foreign_id: str) -> Optional[Player]:
        """Get player by foreign ID"""
        return Player.query.filter_by(foreign_id=foreign_id).first()

    def update_player(self, player_id: int, first_name: str = None,
                     last_name: str = None, team_id: int = None,
                     number: int = None, is_goalkeeper: bool = None,
                     is_captain: bool = None, foreign_id: str = None) -> Optional[Player]:
        """
        Update player

        Args:
            player_id: Player ID
            first_name: New first name (optional)
            last_name: New last name (optional)
            team_id: New team ID (optional)
            number: New jersey number (optional)
            is_goalkeeper: New goalkeeper status (optional)
            is_captain: New captain status (optional)
            foreign_id: New foreign ID (optional)

        Returns:
            Updated Player object or None if error

        Raises:
            ValueError if team not found
        """
        player = self.get_player_by_id(player_id)
        if not player:
            logger.warning(f"Player with ID {player_id} not found")
            return None

        try:
            if first_name is not None:
                player.first_name = first_name
            if last_name is not None:
                player.last_name = last_name
            if team_id is not None:
                team = Team.query.get(team_id)
                if not team:
                    raise ValueError(f"Zespół o ID {team_id} nie istnieje")
                player.team_id = team_id
            if number is not None:
                player.number = number
            if is_goalkeeper is not None:
                player.is_goalkeeper = is_goalkeeper
            if is_captain is not None:
                player.is_captain = is_captain
            if foreign_id is not None:
                player.foreign_id = foreign_id

            db.session.commit()
            logger.info(f"Updated player ID {player_id}")
            return player

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating player: {e}")
            raise

    def delete_player(self, player_id: int) -> bool:
        """
        Delete player
        
        Note: This will also delete all PlayerGame associations (cascade)

        Args:
            player_id: Player ID

        Returns:
            True if deleted, False if error
        """
        player = self.get_player_by_id(player_id)
        if not player:
            logger.warning(f"Player with ID {player_id} not found")
            return False

        try:
            player_name = player.full_name
            db.session.delete(player)
            db.session.commit()
            logger.info(f"Deleted player: {player_name}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting player: {e}")
            return False

    def get_goalkeepers(self, team_id: int = None) -> List[Player]:
        """Get all goalkeepers, optionally filtered by team"""
        query = Player.query.filter_by(is_goalkeeper=True)
        if team_id:
            query = query.filter_by(team_id=team_id)
        return query.order_by(Player.last_name, Player.first_name).all()

    def get_captains(self, team_id: int = None) -> List[Player]:
        """Get all captains, optionally filtered by team"""
        query = Player.query.filter_by(is_captain=True)
        if team_id:
            query = query.filter_by(team_id=team_id)
        return query.order_by(Player.last_name, Player.first_name).all()
