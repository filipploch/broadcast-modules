"""SubstitutionManager — zarządzanie zmianami zawodników (moduł garbarnia).

Logika ról po zmianie zależy od config.RETURN_CHANGES:
  False (domyślnie) — schodzący zawodnik dostaje ROLE_RETIRED (nie wróci)
  True              — schodzący zawodnik dostaje ROLE_SUBSTITUTE (może wrócić)

Publiczne metody tworzenia zmian:
  make_substitution(...)       — jedna zmiana, automatycznie nowa grupa
  make_substitution_group(...) — lista zmian, wszystkie w tej samej nowej grupie,
                                 jeden commit

Usunięcie zmiany cofa role obu zawodników do stanu sprzed zmiany.
Usunięcie jednej zmiany z grupy nie wpływa na pozostałe zmiany w grupie.

Edycja game_time_ms pojedynczej zmiany propaguje nową wartość
na wszystkie zmiany w tej samej grupie (game_id + team_id + substitution_group).
"""
from typing import List, NamedTuple, Optional
from core.extensions import db
from app.models.substitution import Substitution
from app.models.game_player import (
    GamePlayer, ROLE_STARTER, ROLE_SUBSTITUTE, ROLE_RETIRED
)
import logging

logger = logging.getLogger(__name__)


class SubstitutionItem(NamedTuple):
    """Para zawodników do zmiany wielokrotnej."""
    player_in_id:  int
    player_out_id: int


def _return_changes_enabled() -> bool:
    """Odczytaj flagę RETURN_CHANGES z konfiguracji aplikacji."""
    try:
        from flask import current_app
        return current_app.config.get('RETURN_CHANGES', False)
    except RuntimeError:
        return False


def _current_period_id() -> Optional[int]:
    """Odczytaj aktualny period_id z Settings."""
    from app.models.settings import Settings
    return Settings.get_settings().current_period_id


class SubstitutionManager:

    # ── Publiczne API tworzenia ───────────────────────────────────────────────

    def make_substitution(
        self,
        game_id:       int,
        team_id:       int,
        player_in_id:  int,
        player_out_id: int,
        game_time_ms:  int,
    ) -> Substitution:
        """
        Wykonaj pojedynczą zmianę zawodnika (nowa, jednoelementowa grupa).

        period_id odczytywany automatycznie z Settings.current_period_id.
        Gdy None (rzuty karne) — zmiana zapisana bez powiązania z okresem.

        Raises:
            ValueError przy błędach walidacji
        """
        group = self._next_group_number(game_id, team_id)
        subs  = self._make_group(
            game_id=game_id,
            team_id=team_id,
            items=[SubstitutionItem(player_in_id, player_out_id)],
            game_time_ms=game_time_ms,
            substitution_group=group,
        )
        return subs[0]

    def make_substitution_group(
        self,
        game_id:      int,
        team_id:      int,
        items:        List[SubstitutionItem],
        game_time_ms: int,
    ) -> List[Substitution]:
        """
        Wykonaj kilka zmian jednocześnie (wszystkie w tej samej grupie).

        Walidacja odbywa się dla wszystkich par przed zapisem —
        jeśli którakolwiek para jest nieprawidłowa, żadna zmiana nie zostaje zapisana.

        Args:
            items: lista par SubstitutionItem(player_in_id, player_out_id)

        Returns:
            Lista utworzonych obiektów Substitution

        Raises:
            ValueError jeśli lista jest pusta lub którakolwiek para jest nieprawidłowa
        """
        if not items:
            raise ValueError("Lista zmian nie może być pusta")

        group = self._next_group_number(game_id, team_id)
        return self._make_group(
            game_id=game_id,
            team_id=team_id,
            items=items,
            game_time_ms=game_time_ms,
            substitution_group=group,
        )

    # TODO(UI): brak jeszcze przycisku/formularza "Dodaj zmianę wstecznie" —
    # analogiczne do GameEventManager.record_event_at_time(), gotowe do
    # podpięcia pod przyszły formularz (okres + MM:SS -> para zawodników).
    def make_substitution_at_time(
        self,
        game_id:            int,
        team_id:            int,
        player_in_id:       int,
        player_out_id:      int,
        period_id:          int,
        event_time_delta_s: int,
    ) -> Substitution:
        """
        Jak make_substitution(), ale dla WYBRANEGO, niekoniecznie bieżącego
        okresu meczu ("wstecznie" — patrz GameEventManager.record_event_at_time,
        ten sam wzorzec: period_id podawany jawnie zamiast odczytywany z
        Settings.current_period_id, żeby dało się cofnąć do wcześniejszej
        części meczu niż ta aktualnie trwająca).

        Raises:
            ValueError: podany okres nie istnieje/nie należy do meczu, albo
                błąd walidacji pary zawodników (patrz _make_group)
        """
        group = self._next_group_number(game_id, team_id)
        subs = self.make_substitution_group_at_time(
            game_id=game_id,
            team_id=team_id,
            items=[SubstitutionItem(player_in_id, player_out_id)],
            period_id=period_id,
            event_time_delta_s=event_time_delta_s,
        )
        return subs[0]

    def make_substitution_group_at_time(
        self,
        game_id:            int,
        team_id:            int,
        items:              List[SubstitutionItem],
        period_id:          int,
        event_time_delta_s: int,
    ) -> List[Substitution]:
        """Jak make_substitution_group(), ale dla WYBRANEGO okresu — patrz
        make_substitution_at_time()."""
        if not items:
            raise ValueError("Lista zmian nie może być pusta")

        from app.models.period import Period
        period = Period.query.get(period_id)
        if not period or period.game_id != game_id:
            raise ValueError(f"Część o ID {period_id} nie istnieje lub nie należy do meczu {game_id}")

        game_time_ms = period.initial_time + event_time_delta_s * 1000

        group = self._next_group_number(game_id, team_id)
        return self._make_group(
            game_id=game_id,
            team_id=team_id,
            items=items,
            game_time_ms=game_time_ms,
            substitution_group=group,
            period_id=period_id,
        )

    # ── Wewnętrzna implementacja tworzenia ────────────────────────────────────

    def _make_group(
        self,
        game_id:            int,
        team_id:            int,
        items:              List[SubstitutionItem],
        game_time_ms:       int,
        substitution_group: int,
        period_id:          Optional[int] = None,
    ) -> List[Substitution]:
        """
        Wewnętrzna metoda: waliduj wszystkie pary, zapisz w jednej transakcji.
        Numer grupy jest przekazywany z zewnątrz — obliczony raz przed pętlą.

        period_id: jawnie podany okres (mechanizm "wstecznie") albo None,
        żeby odczytać bieżący z Settings.current_period_id (zwykły, żywy flow).
        """
        if period_id is None:
            period_id = _current_period_id()
        role_after_exit    = ROLE_SUBSTITUTE if _return_changes_enabled() else ROLE_RETIRED

        # ── Walidacja wszystkich par przed jakimkolwiek zapisem ───────────────
        validated = []
        for item in items:
            pg_in = GamePlayer.query.filter_by(
                game_id=game_id, team_id=team_id, player_id=item.player_in_id
            ).first()
            pg_out = GamePlayer.query.filter_by(
                game_id=game_id, team_id=team_id, player_id=item.player_out_id
            ).first()

            if not pg_in:
                raise ValueError(
                    f"Zawodnik in (player_id={item.player_in_id}) "
                    f"nie jest przypisany do meczu {game_id} w drużynie {team_id}"
                )
            if not pg_out:
                raise ValueError(
                    f"Zawodnik out (player_id={item.player_out_id}) "
                    f"nie jest przypisany do meczu {game_id} w drużynie {team_id}"
                )
            if pg_in.role != ROLE_SUBSTITUTE:
                raise ValueError(
                    f"Zawodnik in (player_id={item.player_in_id}) musi być rezerowym "
                    f"(aktualnie: {pg_in.role})"
                )
            if pg_out.role != ROLE_STARTER:
                raise ValueError(
                    f"Zawodnik out (player_id={item.player_out_id}) musi być podstawowym "
                    f"(aktualnie: {pg_out.role})"
                )
            validated.append((item, pg_in, pg_out))

        # ── Zapis wszystkich zmian w jednej transakcji ────────────────────────
        try:
            subs = []
            for item, pg_in, pg_out in validated:
                sub = Substitution(
                    game_id=game_id,
                    period_id=period_id,
                    team_id=team_id,
                    player_in_id=item.player_in_id,
                    player_out_id=item.player_out_id,
                    game_time_ms=game_time_ms,
                    substitution_group=substitution_group,
                )
                db.session.add(sub)
                pg_in.role  = ROLE_STARTER
                pg_out.role = role_after_exit
                subs.append(sub)

            db.session.commit()
            logger.info(
                f"Zapisano {len(subs)} zmian(ę) — game={game_id} team={team_id} "
                f"group={substitution_group} t={game_time_ms}ms"
            )
            return subs

        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd zapisu grupy zmian: {e}")
            raise

    def _next_group_number(self, game_id: int, team_id: int) -> int:
        """Kolejny numer grupy zmian dla danego meczu i drużyny."""
        from sqlalchemy import func
        result = db.session.query(
            func.max(Substitution.substitution_group)
        ).filter_by(game_id=game_id, team_id=team_id).scalar()
        return (result or 0) + 1

    # ── Odczyt ────────────────────────────────────────────────────────────────

    def get_substitutions_for_game(
        self, game_id: int, team_id: Optional[int] = None
    ) -> List[Substitution]:
        """Pobierz wszystkie zmiany dla meczu, opcjonalnie filtrując po drużynie."""
        q = Substitution.query.filter_by(game_id=game_id)
        if team_id:
            q = q.filter_by(team_id=team_id)
        return q.order_by(
            Substitution.substitution_group.desc(),
            Substitution.id.asc()
        ).all()

    def get_substitution_by_id(self, sub_id: int) -> Optional[Substitution]:
        return Substitution.query.get(sub_id)

    def get_group(self, game_id: int, team_id: int, group: int) -> List[Substitution]:
        """Pobierz wszystkie zmiany należące do grupy."""
        return Substitution.query.filter_by(
            game_id=game_id, team_id=team_id, substitution_group=group
        ).order_by(Substitution.id.asc()).all()

    # ── Usuwanie zmiany ───────────────────────────────────────────────────────

    def delete_substitution(self, sub_id: int) -> bool:
        """
        Usuń pojedynczą zmianę i cofnij role zawodników.

        Cofnięcie ról:
          - player_in  → ROLE_SUBSTITUTE  (wraca na ławkę)
          - player_out → ROLE_STARTER     (wraca na boisko)

        Uwaga: jeśli zawodnik był zaangażowany w kolejną zmianę po tej,
        cofnięcie może prowadzić do niespójności. Usuwaj zmiany
        od najnowszej wstecz.

        Returns:
            True jeśli usunięto, False jeśli nie znaleziono
        """
        sub = self.get_substitution_by_id(sub_id)
        if not sub:
            logger.warning(f"Zmiana ID {sub_id} nie znaleziona")
            return False

        pg_in  = GamePlayer.query.filter_by(
            game_id=sub.game_id, team_id=sub.team_id, player_id=sub.player_in_id
        ).first()
        pg_out = GamePlayer.query.filter_by(
            game_id=sub.game_id, team_id=sub.team_id, player_id=sub.player_out_id
        ).first()

        try:
            if pg_in:
                pg_in.role  = ROLE_SUBSTITUTE
            if pg_out:
                pg_out.role = ROLE_STARTER

            db.session.delete(sub)
            db.session.commit()
            logger.info(f"Usunięto zmianę ID {sub_id}, przywrócono role zawodników")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd usuwania zmiany {sub_id}: {e}")
            return False

    # ── Edycja zmiany ─────────────────────────────────────────────────────────

    def edit_substitution_players(
        self,
        sub_id:        int,
        player_in_id:  Optional[int] = None,
        player_out_id: Optional[int] = None,
    ) -> Substitution:
        """
        Edytuj player_in_id i/lub player_out_id istniejącej zmiany.

        Waliduje:
          - nowy player_in  musi mieć ROLE_SUBSTITUTE
          - nowy player_out musi mieć ROLE_STARTER
          - zabezpieczenie przed zmianą między dwoma starters lub dwoma substitutes

        Cofa role starych zawodników, nadaje role nowym.

        Returns:
            Zaktualizowany obiekt Substitution

        Raises:
            ValueError przy błędach walidacji
        """
        sub = self.get_substitution_by_id(sub_id)
        if not sub:
            raise ValueError(f"Zmiana ID {sub_id} nie istnieje")

        game_id = sub.game_id
        team_id = sub.team_id
        role_after_exit = ROLE_SUBSTITUTE if _return_changes_enabled() else ROLE_RETIRED

        old_pg_in  = GamePlayer.query.filter_by(
            game_id=game_id, team_id=team_id, player_id=sub.player_in_id
        ).first()
        old_pg_out = GamePlayer.query.filter_by(
            game_id=game_id, team_id=team_id, player_id=sub.player_out_id
        ).first()

        try:
            if player_in_id is not None and player_in_id != sub.player_in_id:
                new_pg_in = GamePlayer.query.filter_by(
                    game_id=game_id, team_id=team_id, player_id=player_in_id
                ).first()
                if not new_pg_in:
                    raise ValueError(
                        f"Nowy player_in (id={player_in_id}) nie jest przypisany "
                        f"do meczu {game_id}"
                    )
                if new_pg_in.role != ROLE_SUBSTITUTE:
                    raise ValueError(
                        f"Nowy player_in (id={player_in_id}) musi być rezerowym "
                        f"(aktualnie: {new_pg_in.role})"
                    )
                if old_pg_in:
                    old_pg_in.role = ROLE_SUBSTITUTE
                new_pg_in.role   = ROLE_STARTER
                sub.player_in_id = player_in_id

            if player_out_id is not None and player_out_id != sub.player_out_id:
                new_pg_out = GamePlayer.query.filter_by(
                    game_id=game_id, team_id=team_id, player_id=player_out_id
                ).first()
                if not new_pg_out:
                    raise ValueError(
                        f"Nowy player_out (id={player_out_id}) nie jest przypisany "
                        f"do meczu {game_id}"
                    )
                if new_pg_out.role != ROLE_STARTER:
                    raise ValueError(
                        f"Nowy player_out (id={player_out_id}) musi być podstawowym "
                        f"(aktualnie: {new_pg_out.role})"
                    )
                if old_pg_out:
                    old_pg_out.role = ROLE_STARTER
                new_pg_out.role   = role_after_exit
                sub.player_out_id = player_out_id

            db.session.commit()
            logger.info(f"Zaktualizowano zmianę ID {sub_id}")
            return sub

        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd edycji zmiany {sub_id}: {e}")
            raise

    def edit_substitution_time(
        self,
        sub_id:       int,
        game_time_ms: int,
    ) -> List[Substitution]:
        """
        Zaktualizuj czas zmiany.

        Nowy game_time_ms jest propagowany na wszystkie zmiany
        należące do tej samej grupy (game_id + team_id + substitution_group).

        Returns:
            Lista wszystkich zaktualizowanych Substitution w grupie
        """
        sub = self.get_substitution_by_id(sub_id)
        if not sub:
            raise ValueError(f"Zmiana ID {sub_id} nie istnieje")

        group_subs = self.get_group(sub.game_id, sub.team_id, sub.substitution_group)

        try:
            for s in group_subs:
                s.game_time_ms = game_time_ms
            db.session.commit()
            logger.info(
                f"Zaktualizowano czas grupy {sub.substitution_group} "
                f"meczu {sub.game_id} team {sub.team_id} "
                f"→ {game_time_ms} ms ({len(group_subs)} zmian)"
            )
            return group_subs

        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd aktualizacji czasu zmiany {sub_id}: {e}")
            raise