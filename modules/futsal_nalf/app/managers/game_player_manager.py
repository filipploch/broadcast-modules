"""GamePlayer Manager - handles player assignments to games"""
from typing import List, Optional
from app.extensions import db
from app.models.game_player import GamePlayer
from core.models.player import Player
from core.models.game import Game
import logging

logger = logging.getLogger(__name__)


class GamePlayerManager:
    """Manager for GamePlayer operations"""

    def assign_player_to_game(self, player_id: int, game_id: int,
                              override_team_id: int = None,
                              override_is_goalkeeper: bool = None,
                              override_is_captain: bool = None,
                              override_number: int = None) -> Optional[GamePlayer]:
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
            GamePlayer object or None if error

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
        existing = GamePlayer.query.filter_by(player_id=player_id, game_id=game_id).first()
        if existing:
            raise ValueError(f"Zawodnik {player.full_name} jest już przypisany do meczu {game_id}")

        try:
            # Create snapshot (use overrides if provided, else copy from player)
            game_player = GamePlayer(
                player_id=player_id,
                game_id=game_id,
                team_id=override_team_id if override_team_id is not None else player.team_id,
                is_goalkeeper=override_is_goalkeeper if override_is_goalkeeper is not None else player.is_goalkeeper,
                is_captain=override_is_captain if override_is_captain is not None else player.is_captain,
                number=override_number if override_number is not None else player.number
            )
            db.session.add(game_player)
            db.session.commit()

            logger.info(f"Assigned player {player.full_name} to game {game_id}")
            return game_player

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning player to game: {e}")
            raise

    def assign_team_to_game(self, team_id: int, game_id: int) -> List[GamePlayer]:
        """
        Assign all players from a team to a game
        
        Creates snapshots for all players in the team.

        Args:
            team_id: Team ID
            game_id: Game ID

        Returns:
            List of created GamePlayer objects
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

    def get_players_for_game(self, game_id: int, team_id: int = None) -> List[GamePlayer]:
        """
        Get all players assigned to a game
        
        Args:
            game_id: Game ID
            team_id: Optional filter by team

        Returns:
            List of GamePlayer objects
        """
        query = GamePlayer.query.filter_by(game_id=game_id)
        if team_id:
            query = query.filter_by(team_id=team_id)
        return query.join(Player, GamePlayer.player_id == Player.id).order_by(
            GamePlayer.is_goalkeeper.desc(),     # bramkarze pierwsi
            GamePlayer.number.asc().nullslast(), # numer rosnąco, None na końcu
            Player.last_name.asc(),              # nazwisko alfabetycznie
        ).all()

    def get_game_player_by_id(self, game_player_id: int) -> Optional[GamePlayer]:
        """Get GamePlayer by ID"""
        return GamePlayer.query.get(game_player_id)
    
    def get_game_player_by_player_id(self, player_id: int) -> Optional[GamePlayer]:
        """Get GamePlayer by ID"""
        return GamePlayer.query.filter_by(player_id=player_id).first()

    def update_game_player(self, game_player_id: int,
                          team_id: int = None,
                          is_goalkeeper: bool = None,
                          is_captain: bool = None,
                          number: int = None) -> Optional[GamePlayer]:
        """
        Update player game assignment
        
        Note: This updates the historical snapshot for this specific game.

        Args:
            game_player_id: GamePlayer ID
            team_id: New team ID (optional)
            is_goalkeeper: New goalkeeper status (optional)
            is_captain: New captain status (optional)
            number: New jersey number (optional)

        Returns:
            Updated GamePlayer object or None if error
        """
        game_player = self.get_game_player_by_id(game_player_id)
        if not game_player:
            logger.warning(f"GamePlayer with ID {game_player_id} not found")
            return None

        try:
            if team_id is not None:
                game_player.team_id = team_id
            if is_goalkeeper is not None:
                game_player.is_goalkeeper = is_goalkeeper
            if is_captain is not None:
                game_player.is_captain = is_captain
            if number is not None:
                game_player.number = number

            db.session.commit()
            logger.info(f"Updated GamePlayer ID {game_player_id}")
            return game_player

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating player game: {e}")
            return None

    def remove_player_from_game(self, game_player_id: int) -> bool:
        """
        Remove player from game

        Args:
            game_player_id: GamePlayer ID

        Returns:
            True if removed, False if error
        """
        game_player = self.get_game_player_by_id(game_player_id)
        if not game_player:
            logger.warning(f"GamePlayer with ID {game_player_id} not found")
            return False

        try:
            db.session.delete(game_player)
            db.session.commit()
            logger.info(f"Removed player from game (GamePlayer ID: {game_player_id})")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing player from game: {e}")
            return False

    def get_games_for_player(self, player_id: int) -> List[GamePlayer]:
        """Get all games where player participated"""
        return GamePlayer.query.filter_by(player_id=player_id).all()
