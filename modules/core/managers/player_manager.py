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


def _get_player_foreign_id():
    from core.models.base_player_foreign_id import get_player_foreign_id_model
    return get_player_foreign_id_model()


class PlayerManager:

    def create_player(self, first_name: str, last_name: str, team_id: int,
                      number: int = None, is_goalkeeper: bool = False,
                      is_captain: bool = False):
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

    def get_players_without_team(self):
        """Zawodnicy bez przypisanej drużyny (np. po wykryciu odejścia przez scraper)."""
        Player = _get_player()
        return Player.query.filter_by(team_id=None).order_by(
            Player.last_name, Player.first_name
        ).all()

    def remove_player_from_team(self, player_id: int):
        """Wyzeruj team_id zawodnika (staje się wolnym agentem). Historia meczowa
        (GamePlayer) nie jest tym ruszana — przechowuje własny snapshot team_id."""
        player = self.get_player_by_id(player_id)
        if not player:
            logger.warning(f"Player with ID {player_id} not found")
            return None
        player.team_id = None
        db.session.commit()
        logger.info(f"Removed player ID {player_id} from team (now without team)")
        return player

    def get_player_by_id(self, player_id: int):
        Player = _get_player()
        return Player.query.get(player_id)

    def get_player_by_foreign_id(self, scraper_id, foreign_id: str):
        """Get player mapped to foreign_id for a given scraper"""
        PlayerForeignId = _get_player_foreign_id()
        local_id = PlayerForeignId.get_local_id(scraper_id, foreign_id)
        return self.get_player_by_id(local_id) if local_id else None

    def set_player_foreign_id(self, player_id, scraper_id, foreign_id):
        """Create/update the (scraper, player) -> foreign_id mapping"""
        PlayerForeignId = _get_player_foreign_id()
        return PlayerForeignId.set_foreign_id(scraper_id, player_id, foreign_id)

    def update_player(self, player_id: int, first_name: str = None,
                      last_name: str = None, team_id: int = None,
                      number: int = None, is_goalkeeper: bool = None,
                      is_captain: bool = None):
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
