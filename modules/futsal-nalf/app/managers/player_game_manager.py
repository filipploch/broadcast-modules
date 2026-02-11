"""PlayerGame Manager - handles player assignments to games"""
from typing import List, Optional
from app.extensions import db
from app.models.player_game import PlayerGame
from app.models.player import Player
from app.models.game import Game
import logging

logger = logging.getLogger(__name__)


class PlayerGameManager:
    """Manager for PlayerGame operations"""

    def assign_player_to_game(self, player_id: int, game_id: int,
                              override_team_id: int = None,
                              override_is_goalkeeper: bool = None,
                              override_is_captain: bool = None,
                              override_number: int = None) -> Optional[PlayerGame]:
        """
        Assign player to game (creates historical snapshot)
        
        By default, copies current player data (team_id, is_goalkeeper, is_captain, number).
        Use override parameters to set different values for this specific game.

        Args:
            player_id: Player ID
            game_id: Game ID
            override_team_id: Override team_id (default: use Player.team_id)
            override_is_goalkeeper: Override is_goalkeeper (default: use Player.is_goalkeeper)
            override_is_captain: Override is_captain (default: use Player.is_captain)
            override_number: Override number (default: use Player.number)

        Returns:
            PlayerGame object or None if error

        Raises:
            ValueError if player/game not found or player already assigned
        """
        # Validate player exists
        player = Player.query.get(player_id)
        if not player:
            raise ValueError(f"Zawodnik o ID {player_id} nie istnieje")

        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Check if player already assigned
        existing = PlayerGame.query.filter_by(player_id=player_id, game_id=game_id).first()
        if existing:
            raise ValueError(f"Zawodnik {player.full_name} jest już przypisany do meczu {game_id}")

        try:
            # Create snapshot (use overrides if provided, else copy from player)
            player_game = PlayerGame(
                player_id=player_id,
                game_id=game_id,
                team_id=override_team_id if override_team_id is not None else player.team_id,
                is_goalkeeper=override_is_goalkeeper if override_is_goalkeeper is not None else player.is_goalkeeper,
                is_captain=override_is_captain if override_is_captain is not None else player.is_captain,
                number=override_number if override_number is not None else player.number
            )
            db.session.add(player_game)
            db.session.commit()

            logger.info(f"Assigned player {player.full_name} to game {game_id}")
            return player_game

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning player to game: {e}")
            raise

    def assign_team_to_game(self, team_id: int, game_id: int) -> List[PlayerGame]:
        """
        Assign all players from a team to a game
        
        Creates snapshots for all players in the team.

        Args:
            team_id: Team ID
            game_id: Game ID

        Returns:
            List of created PlayerGame objects
        """
        players = Player.query.filter_by(team_id=team_id).all()
        
        assigned = []
        for player in players:
            try:
                pg = self.assign_player_to_game(player.id, game_id)
                assigned.append(pg)
            except ValueError as e:
                logger.warning(f"Skipping player {player.id}: {e}")
                continue

        logger.info(f"Assigned {len(assigned)} players from team {team_id} to game {game_id}")
        return assigned

    def get_players_for_game(self, game_id: int, team_id: int = None) -> List[PlayerGame]:
        """
        Get all players assigned to a game
        
        Args:
            game_id: Game ID
            team_id: Optional filter by team

        Returns:
            List of PlayerGame objects
        """
        query = PlayerGame.query.filter_by(game_id=game_id)
        if team_id:
            query = query.filter_by(team_id=team_id)
        return query.order_by(
            PlayerGame.number.asc().nullslast()
        ).all()

    def get_player_game_by_id(self, player_game_id: int) -> Optional[PlayerGame]:
        """Get PlayerGame by ID"""
        return PlayerGame.query.get(player_game_id)

    def update_player_game(self, player_game_id: int,
                          team_id: int = None,
                          is_goalkeeper: bool = None,
                          is_captain: bool = None,
                          number: int = None) -> Optional[PlayerGame]:
        """
        Update player game assignment
        
        Note: This updates the historical snapshot for this specific game.

        Args:
            player_game_id: PlayerGame ID
            team_id: New team ID (optional)
            is_goalkeeper: New goalkeeper status (optional)
            is_captain: New captain status (optional)
            number: New jersey number (optional)

        Returns:
            Updated PlayerGame object or None if error
        """
        player_game = self.get_player_game_by_id(player_game_id)
        if not player_game:
            logger.warning(f"PlayerGame with ID {player_game_id} not found")
            return None

        try:
            if team_id is not None:
                player_game.team_id = team_id
            if is_goalkeeper is not None:
                player_game.is_goalkeeper = is_goalkeeper
            if is_captain is not None:
                player_game.is_captain = is_captain
            if number is not None:
                player_game.number = number

            db.session.commit()
            logger.info(f"Updated PlayerGame ID {player_game_id}")
            return player_game

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating player game: {e}")
            return None

    def remove_player_from_game(self, player_game_id: int) -> bool:
        """
        Remove player from game

        Args:
            player_game_id: PlayerGame ID

        Returns:
            True if removed, False if error
        """
        player_game = self.get_player_game_by_id(player_game_id)
        if not player_game:
            logger.warning(f"PlayerGame with ID {player_game_id} not found")
            return False

        try:
            db.session.delete(player_game)
            db.session.commit()
            logger.info(f"Removed player from game (PlayerGame ID: {player_game_id})")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing player from game: {e}")
            return False

    def get_games_for_player(self, player_id: int) -> List[PlayerGame]:
        """Get all games where player participated"""
        return PlayerGame.query.filter_by(player_id=player_id).all()
