"""ShootoutKick Manager - operacje na rzutach karnych w konkursie"""
from typing import Optional, List
from core.extensions import db

def _get_kick():
    from core.models.shootout_kick import get_shootout_kick_model
    return get_shootout_kick_model()


def _get_shootout():
    from core.models.shootout import get_shootout_model
    return get_shootout_model()

import logging

logger = logging.getLogger(__name__)


class ShootoutKickManager:
    """Manager dla pojedynczych rzutów w konkursie rzutów karnych."""

    # =========================================================================
    # TWORZENIE RZUTU
    # =========================================================================

    def add_kick(self, shootout_id: int, game_id: int, team: str,
                 round_number: int, kick_order: int, player_id: int):
        """
        Dodaj rzut do kolejki (wynik jeszcze nieznany — scored=None).

        Args:
            shootout_id:  ID konkursu (Shootout)
            game_id:      ID meczu (Game) — redundantny FK dla szybkich zapytań
            team:         'home' lub 'away'
            round_number: numer kolejki (min. ShootoutKick.MIN_ROUNDS = 3)
            kick_order:   pozycja w kolejce (1 = home strzela, 2 = away strzela)
            player_id:    ID zawodnika (Player) — wymagany

        Returns:
            ShootoutKick

        Raises:
            ValueError przy nieprawidłowych danych lub duplikacie pozycji
        """
        ShootoutKick = _get_kick()
        Shootout = _get_shootout()
        if team not in ShootoutKick.VALID_TEAMS:
            raise ValueError(
                f"Nieprawidłowa drużyna: '{team}'. "
                f"Dozwolone: {', '.join(ShootoutKick.VALID_TEAMS)}"
            )

        # Weryfikuj spójność game_id z Shootout
        shootout = Shootout.query.get(shootout_id)
        if not shootout:
            raise ValueError(f"Shootout id={shootout_id} nie istnieje")
        if shootout.game_id != game_id:
            raise ValueError(
                f"game_id={game_id} niezgodne z konkursem "
                f"(shootout.game_id={shootout.game_id})"
            )

        if round_number < 1:
            raise ValueError(f"round_number musi być >= 1, otrzymano {round_number}")

        existing = ShootoutKick.query.filter_by(
            shootout_id=shootout_id,
            round_number=round_number,
            kick_order=kick_order,
        ).first()
        if existing:
            raise ValueError(
                f"Pozycja już zajęta: konkurs={shootout_id}, "
                f"kolejka={round_number}, pozycja={kick_order}"
            )

        kick = ShootoutKick(
            shootout_id=shootout_id,
            game_id=game_id,
            team=team,
            round_number=round_number,
            kick_order=kick_order,
            player_id=player_id,
        )
        db.session.add(kick)
        db.session.commit()

        logger.info(
            f"Dodano rzut: konkurs={shootout_id} mecz={game_id} kolejka={round_number} "
            f"pozycja={kick_order} drużyna={team} zawodnik={player_id}"
        )
        return kick

    # =========================================================================
    # REJESTRACJA WYNIKU
    # =========================================================================

    def set_kick_result(self, kick_id: int, scored: bool) -> Optional[ShootoutKick]:
        ShootoutKick = _get_kick()
        Shootout = _get_shootout()
        """
        Ustaw wynik rzutu i zsynchronizuj licznik bramek w Shootout.

        Args:
            kick_id: ID rzutu (ShootoutKick)
            scored:  True = bramka, False = brak bramki

        Returns:
            Zaktualizowany ShootoutKick lub None jeśli nie znaleziono
        """
        ShootoutKick = _get_kick()
        kick = ShootoutKick.query.get(kick_id)
        if not kick:
            logger.warning(f"ShootoutKick id={kick_id} nie istnieje")
            return None

        kick.set_result(scored)
        self._sync_shootout_score(kick.shootout_id)
        db.session.commit()

        result_str = 'BRAMKA' if scored else 'BRAK BRAMKI'
        logger.info(f"Wynik rzutu id={kick_id}: {result_str} (konkurs={kick.shootout_id})")
        return kick

    # =========================================================================
    # ODCZYT
    # =========================================================================

    def get_kicks_for_shootout(self, shootout_id: int) -> List[ShootoutKick]:
        ShootoutKick = _get_kick()
        Shootout = _get_shootout()
        """Wszystkie rzuty dla danego konkursu, posortowane po kolejce i pozycji."""
        return (ShootoutKick.query
                .filter_by(shootout_id=shootout_id)
                .order_by(ShootoutKick.round_number, ShootoutKick.kick_order)
                .all())

    def get_kicks_by_round(self, shootout_id: int,
                           round_number: int) -> List[ShootoutKick]:
        """Rzuty z konkretnej kolejki."""
        ShootoutKick = _get_kick()
        return (ShootoutKick.query
                .filter_by(shootout_id=shootout_id, round_number=round_number)
                .order_by(ShootoutKick.kick_order)
                .all())

    def get_kicks_by_team(self, shootout_id: int,
                          team: str) -> List[ShootoutKick]:
        """Wszystkie rzuty jednej drużyny."""
        ShootoutKick = _get_kick()
        return (ShootoutKick.query
                .filter_by(shootout_id=shootout_id, team=team)
                .order_by(ShootoutKick.round_number, ShootoutKick.kick_order)
                .all())


    def get_kicks_by_game(self, game_id: int) -> List[ShootoutKick]:
        ShootoutKick = _get_kick()
        Shootout = _get_shootout()
        """Wszystkie rzuty dla danego meczu (bez potrzeby JOIN przez Shootout)."""
        return (ShootoutKick.query
                .filter_by(game_id=game_id)
                .order_by(ShootoutKick.round_number, ShootoutKick.kick_order)
                .all())

    def get_scoreboard(self, shootout_id: int) -> dict:
        """
        Pełny stan konkursu.

        Returns:
            {
              'home': { 'goals': int, 'kicks_taken': int },
              'away': { 'goals': int, 'kicks_taken': int },
              'total_rounds': int,   # ile kolejek już dodano
              'rounds': [
                  {
                    'round': int,
                    'home': kick_dict | None,   # None = jeszcze nieprzypisany
                    'away': kick_dict | None,
                  },
                  ...
              ]
            }
        """
        kicks = self.get_kicks_for_shootout(shootout_id)

        home_goals  = sum(1 for k in kicks if k.team == 'home' and k.scored is True)
        away_goals  = sum(1 for k in kicks if k.team == 'away' and k.scored is True)
        home_taken  = sum(1 for k in kicks if k.team == 'home' and not k.is_pending)
        away_taken  = sum(1 for k in kicks if k.team == 'away' and not k.is_pending)

        rounds_map: dict = {}
        for k in kicks:
            rnd = rounds_map.setdefault(k.round_number, {'home': None, 'away': None})
            rnd[k.team] = k.to_dict()

        rounds = [
            {'round': rn, **data}
            for rn, data in sorted(rounds_map.items())
        ]

        return {
            'home': {'goals': home_goals, 'kicks_taken': home_taken},
            'away': {'goals': away_goals, 'kicks_taken': away_taken},
            'total_rounds': len(rounds_map),
            'rounds': rounds,
        }

    def get_current_round(self, shootout_id: int) -> int:
        ShootoutKick = _get_kick()
        Shootout = _get_shootout()
        """
        Zwraca numer aktualnej (ostatniej nieukończonej) kolejki.
        Jeśli wszystkie kolejki mają wyniki dla obu drużyn — zwraca numer następnej.
        Minimum: ShootoutKick.MIN_ROUNDS.
        """
        kicks = self.get_kicks_for_shootout(shootout_id)
        if not kicks:
            return 1

        max_round = max(k.round_number for k in kicks)

        # Sprawdź czy w ostatniej kolejce oba rzuty są wykonane
        last_round_kicks = [k for k in kicks if k.round_number == max_round]
        all_done = all(not k.is_pending for k in last_round_kicks)
        both_teams = {k.team for k in last_round_kicks} == {'home', 'away'}

        if all_done and both_teams:
            return max_round + 1
        return max_round

    # =========================================================================
    # USUWANIE
    # =========================================================================

    def remove_kick(self, kick_id: int) -> bool:
        ShootoutKick = _get_kick()
        Shootout = _get_shootout()
        """Usuń rzut i przelicz wynik w Shootout. Zwraca True jeśli usunięto."""
        kick = ShootoutKick.query.get(kick_id)
        if not kick:
            logger.warning(f"ShootoutKick id={kick_id} nie istnieje")
            return False

        shootout_id = kick.shootout_id
        db.session.delete(kick)
        self._sync_shootout_score(shootout_id)
        db.session.commit()

        logger.info(f"Usunięto rzut id={kick_id}")
        return True

    # =========================================================================
    # PRYWATNE
    # =========================================================================

    def _sync_shootout_score(self, shootout_id: int):
        ShootoutKick = _get_kick()
        Shootout = _get_shootout()
        """
        Przelicz sumaryczny wynik i zapisz w tabeli Shootout.
        Nie commituje — wywołujący zarządza transakcją.
        """
        ShootoutKick = _get_kick()
        Shootout = _get_shootout()
        shootout = Shootout.query.get(shootout_id)
        if not shootout:
            return

        kicks = ShootoutKick.query.filter_by(shootout_id=shootout_id).all()
        shootout.home_team_shootouts = sum(
            1 for k in kicks if k.team == 'home' and k.scored is True
        )
        shootout.away_team_shootouts = sum(
            1 for k in kicks if k.team == 'away' and k.scored is True
        )
        logger.debug(
            f"Sync wynik konkursu {shootout_id}: "
            f"{shootout.home_team_shootouts}:{shootout.away_team_shootouts}"
        )