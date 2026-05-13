"""Player Manager - handles CRUD operations for Player model"""
from core.extensions import db
import logging

logger = logging.getLogger(__name__)


def _get_player():
    from core.models.base_player import get_player_model
    return get_player_model()


def _get_team():
    from core.models.base_team import get_team_model
    return get_team_model()


class PlayerManager:

    def create_player(self, first_name: str, last_name: str, team_id: int,
                      number: int = None, is_goalkeeper: bool = False,
                      is_captain: bool = False, foreign_id: str = None):
        Team = _get_team()
        team = Team.query.get(team_id)
        if not team:
            raise ValueError(f"Zespół o ID {team_id} nie istnieje")

        try:
            Player = _get_player()
            player = Player(
                first_name=first_name,
                last_name=last_name,
                team_id=team_id,
                number=number,
                is_goalkeeper=is_goalkeeper,
                is_captain=is_captain,
                foreign_id=foreign_id,
            )
            db.session.add(player)
            db.session.commit()
            logger.info(f"Created player: {player.full_name} (Team: {team.name})")
            return player
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating player: {e}")
            raise

    def get_all_players(self):
        Player = _get_player()
        return Player.query.order_by(Player.last_name, Player.first_name).all()

    def get_players_by_team(self, team_id: int):
        Player = _get_player()
        return Player.query.filter_by(team_id=team_id).order_by(
            Player.is_goalkeeper.desc(),
            Player.number.asc().nullslast(),
            Player.last_name.asc(),
        ).all()

    def get_player_by_id(self, player_id: int):
        Player = _get_player()
        return Player.query.get(player_id)

    def get_player_by_foreign_id(self, foreign_id: str):
        Player = _get_player()
        return Player.query.filter_by(foreign_id=foreign_id).first()

    def update_player(self, player_id: int, first_name: str = None,
                      last_name: str = None, team_id: int = None,
                      number: int = None, is_goalkeeper: bool = None,
                      is_captain: bool = None, foreign_id: str = None):
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
                Team = _get_team()
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

    def get_goalkeepers(self, team_id: int = None):
        Player = _get_player()
        query = Player.query.filter_by(is_goalkeeper=True)
        if team_id:
            query = query.filter_by(team_id=team_id)
        return query.order_by(Player.last_name, Player.first_name).all()

    def get_captains(self, team_id: int = None):
        Player = _get_player()
        query = Player.query.filter_by(is_captain=True)
        if team_id:
            query = query.filter_by(team_id=team_id)
        return query.order_by(Player.last_name, Player.first_name).all()
