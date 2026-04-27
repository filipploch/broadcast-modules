"""GamePlayerManager — moduł garbarnia.

Nadpisuje assign_player_to_game (dodaje: role, is_youth)
i dodaje get_starters / get_substitutes.
"""
from core.managers.game_player_manager import GamePlayerManager as _CoreGPM
from app.models.game_player import GamePlayer
from app.models.player import Player
import logging

logger = logging.getLogger(__name__)


class GamePlayerManager(_CoreGPM):
    """GamePlayerManager dla garbarni — obsługuje role zawodników."""

    def assign_player_to_game(
        self,
        player_id: int,
        game_id: int,
        role: str = 'starter',
        override_team_id: int = None,
        override_is_goalkeeper: bool = None,
        override_is_captain: bool = None,
        override_is_youth: bool = None,
        override_number: int = None,
    ):
        """Nadpisuje metodę core — dodaje parametr role i is_youth."""
        from app.models.game_player import ROLE_STARTER, VALID_ROLES
        from core.extensions import db


        player = Player.query.get(player_id)
        if not player:
            raise ValueError(f"Zawodnik o ID {player_id} nie istnieje")

        from core.models.base_game import get_game_model
        game = get_game_model().query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        existing = GamePlayer.query.filter_by(
            player_id=player_id, game_id=game_id
        ).first()
        if existing:
            raise ValueError(
                f"Zawodnik {player.full_name} jest już przypisany do meczu {game_id}"
            )

        if role not in VALID_ROLES:
            raise ValueError(f"Nieprawidłowa rola: {role}. Dozwolone: {VALID_ROLES}")

        try:
            game_player = GamePlayer(
                player_id=player_id,
                game_id=game_id,
                team_id=override_team_id if override_team_id is not None else player.team_id,
                is_goalkeeper=override_is_goalkeeper if override_is_goalkeeper is not None
                              else player.is_goalkeeper,
                is_captain=override_is_captain if override_is_captain is not None
                           else player.is_captain,
                is_youth=override_is_youth if override_is_youth is not None
                         else getattr(player, 'is_youth', False),
                number=override_number if override_number is not None else player.number,
                role=role,
            )
            db.session.add(game_player)
            db.session.commit()
            logger.info(f"Przypisano {player.full_name} do meczu {game_id} (rola: {role})")
            return game_player
        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd przypisania zawodnika: {e}")
            raise

    def get_players_for_game(self, game_id: int, team_id: int = None,
                              role: str = None):
        """Nadpisuje metodę core — dodaje filtr role."""

        query = GamePlayer.query.filter_by(game_id=game_id)
        if team_id:
            query = query.filter_by(team_id=team_id)
        if role:
            query = query.filter_by(role=role)
        return query.join(Player, GamePlayer.player_id == Player.id).order_by(
            GamePlayer.is_goalkeeper.desc(),
            GamePlayer.number.asc().nullslast(),
            Player.last_name.asc(),
        ).all()

    def get_starters(self, game_id: int, team_id: int = None):
        return self.get_players_for_game(game_id, team_id=team_id, role='starter')

    def get_substitutes(self, game_id: int, team_id: int = None):
        return self.get_players_for_game(game_id, team_id=team_id, role='substitute')

    def update_game_player(self, game_player_id: int, team_id: int = None,
                            is_goalkeeper: bool = None, is_captain: bool = None,
                            is_youth: bool = None, number: int = None,
                            role: str = None):
        """Nadpisuje metodę core — dodaje is_youth i role."""
        from app.models.game_player import VALID_ROLES
        from core.extensions import db

        game_player = self.get_game_player_by_id(game_player_id)
        if not game_player:
            return None
        if role is not None and role not in VALID_ROLES:
            raise ValueError(f"Nieprawidłowa rola: {role}")
        try:
            if team_id       is not None: game_player.team_id       = team_id
            if is_goalkeeper is not None: game_player.is_goalkeeper = is_goalkeeper
            if is_captain    is not None: game_player.is_captain    = is_captain
            if is_youth      is not None: game_player.is_youth      = is_youth
            if number        is not None: game_player.number        = number
            if role          is not None: game_player.role          = role
            db.session.commit()
            return game_player
        except Exception as e:
            db.session.rollback()
            raise
