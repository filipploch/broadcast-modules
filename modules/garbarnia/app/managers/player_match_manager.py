"""Player Match Manager - workflow scrapera kadry drużyny (scrape → dopasowanie
kandydatów → ręczne zatwierdzenie w PendingPlayerMatch).

Analogiczny do team_scraper_manager.py, ale dla zawodników pojedynczej
drużyny zamiast drużyn ligi. Trenera (Team.coach) ustawia bezpośrednio przy
scrapowaniu — to pojedyncza wartość tekstowa na drużynę, nie wymaga
dopasowania encji jak zawodnik.

Scraper nigdy nie łączy automatycznie znalezionego na www zawodnika z
rekordem Player w bazie — tylko proponuje najbardziej prawdopodobnego
kandydata po podobieństwie imienia i nazwiska. Wiąże to dopiero
resolve_pending_player_match(), wywołane z ekranu przeglądu po decyzji admina.
"""
import difflib
import logging
from typing import Dict, List, Optional

from core.extensions import db
from core.managers.player_manager import PlayerManager
from app.models.team import Team
from app.models.player import Player
from app.models.scraper import Scraper
from app.models.pending_player_match import PendingPlayerMatch
from app.models.pending_player_departure import PendingPlayerDeparture
from app.models.player_foreign_id import PlayerForeignId
from app.managers.scrapers.superscore.superscore_player_scraper import SuperscorePlayerScraper

SIMILARITY_THRESHOLD = 0.6

logger = logging.getLogger(__name__)

player_manager = PlayerManager()


def _superscore_scraper_id() -> int:
    scraper = Scraper.get_by_folder('superscore')
    if not scraper:
        raise RuntimeError("Scraper 'superscore' nie jest zarejestrowany w tabeli scrapers")
    return scraper.id


def _laczynaspilka_scraper_id() -> int:
    scraper = Scraper.get_by_folder('laczynaspilka')
    if not scraper:
        raise RuntimeError("Scraper 'laczynaspilka' nie jest zarejestrowany w tabeli scrapers")
    return scraper.id


def _normalize(name: str) -> str:
    return ' '.join(name.lower().split())


def _best_match(first_name: str, last_name: str, candidates: List[Player]):
    """Zwraca (Player|None, score) najbardziej podobnego zawodnika wśród candidates."""
    norm_name = _normalize(f'{first_name} {last_name}')
    best_player = None
    best_score = 0.0
    for player in candidates:
        score = difflib.SequenceMatcher(
            None, norm_name, _normalize(f'{player.first_name} {player.last_name}')
        ).ratio()
        if score > best_score:
            best_score = score
            best_player = player
    if best_score >= SIMILARITY_THRESHOLD:
        return best_player, best_score
    return None, best_score


class PlayerMatchManager:
    """Workflow scrapowania/dopasowywania kadry drużyny (zawodnicy + trener)."""

    def scrape_team_players_from_superscore(self, team_id: int) -> Dict[str, int]:
        """
        Pobierz kadrę drużyny z superscore.live i zapisz kandydatów-zawodników
        do dopasowania w PendingPlayerMatch. Trenera zapisuje od razu do
        Team.coach (nadpisuje poprzednią wartość).

        Zawodnicy aktualnie przypisani do tej drużyny w bazie, którzy mają już
        foreign_id tego scrapera (czyli byli wcześniej świadomie dopasowani),
        ale nie występują w świeżo pobranym składzie, trafiają do
        PendingPlayerDeparture — czekają na potwierdzenie odejścia, nie są
        usuwani automatycznie.

        Returns:
            {'new_matches': liczba nowych/odświeżonych PendingPlayerMatch,
             'departed': liczba wpisów w kolejce odejść po synchronizacji}

        Raises:
            ValueError: brak drużyny, brak przypisanego superscore foreign_id,
                albo błąd pobierania danych z API.
        """
        team = Team.query.get(team_id)
        if not team:
            raise ValueError("Nie znaleziono drużyny")

        scraper_id = _superscore_scraper_id()
        team_foreign_id = team.get_foreign_id(scraper_id)
        if not team_foreign_id:
            raise ValueError(
                "Drużyna nie ma jeszcze przypisanego superscore foreign_id — "
                "najpierw dopasuj drużynę do ligi przez scraper drużyn"
            )
        team_hash = team_foreign_id.split('/')[-1]

        try:
            squad = SuperscorePlayerScraper().scrape_squad(team_hash)
        except RuntimeError as e:
            raise ValueError(str(e)) from e

        if squad.get('manager_name'):
            team.coach = squad['manager_name']
            db.session.commit()

        return self._queue_scraped_players(team, scraper_id, squad['players'])

    def scrape_team_players_from_laczynaspilka(self, team_id: int) -> Dict[str, int]:
        """
        Pobierz kadrę drużyny z lokalnie zapisanego pliku HTML laczynaspilka.pl
        (np. przez SingleFile — ten sam plik co dotychczasowy auto-sync scraper
        w player_scraper_manager.py) i zapisz kandydatów-zawodników do
        dopasowania w PendingPlayerMatch — analogicznie do superscore, nic nie
        jest linkowane automatycznie.

        Laczynaspilka nie udostępnia danych trenera na karcie drużyny — Team.coach
        nie jest tu ruszane (inaczej niż przy superscore).

        Returns:
            {'new_matches': ..., 'departed': ...}

        Raises:
            ValueError: brak drużyny, brak przypisanego foreign_id (UUID) albo
                brak zapisanego pliku HTML w katalogu tymczasowym.
        """
        from flask import current_app
        import sys
        from app.managers.scrapers.laczynaspilka.player_scraper import PlayerScraper

        team = Team.query.get(team_id)
        if not team:
            raise ValueError("Nie znaleziono drużyny")

        scraper_id = _laczynaspilka_scraper_id()
        team_foreign_id = team.get_foreign_id(scraper_id)
        if not team_foreign_id:
            raise ValueError(
                "Drużyna nie ma skonfigurowanego foreign_id dla laczynaspilka.pl"
            )

        temp_dir = sys.path[0] + current_app.config['TEMP_DIR']
        html_scraper = PlayerScraper()
        html_path = html_scraper.find_html_file_for_team(temp_dir, team_foreign_id)
        if not html_path:
            raise ValueError(
                "Nie znaleziono zapisanego pliku HTML dla tej drużyny w katalogu tymczasowym — "
                f"pobierz i zapisz stronę https://www.laczynaspilka.pl/rozgrywki/druzyna/{team_foreign_id} "
                "(np. wtyczką SingleFile) przed scrapowaniem."
            )

        squad_players = html_scraper.scrape_players_from_html(html_path, team_foreign_id)
        result = self._queue_scraped_players(team, scraper_id, squad_players)

        html_path.unlink(missing_ok=True)
        return result

    def _queue_scraped_players(self, team: Team, scraper_id: int, scraped_players: List[Dict]) -> Dict[str, int]:
        """
        Wspólna logika dla wszystkich scraperów kadry: zawodnik już dopasowany
        wcześniej (ma wpis w PlayerForeignId dla tego scrapera) dostaje tylko
        backfill team_id jeśli zmienił drużynę; reszta trafia do
        PendingPlayerMatch z podpowiedzią po podobieństwie imienia/nazwiska.
        Zawodnicy przypisani do drużyny w bazie, którzy mieli foreign_id tego
        scrapera ale nie występują już w świeżym składzie, trafiają do
        PendingPlayerDeparture (nic nie usuwane automatycznie).

        Wpisy scraped bez foreign_id są pomijane — bez stabilnego identyfikatora
        nie da się ich bezpiecznie odróżnić od już zatwierdzonych zawodników
        przy kolejnym scrapowaniu.
        """
        already_resolved = {
            row.foreign_id: row.player_id
            for row in PlayerForeignId.query.filter_by(scraper_id=scraper_id).all()
        }
        all_players = Player.query.order_by(Player.last_name, Player.first_name).all()

        scraped_foreign_ids = set()
        new_matches = 0
        for scraped in scraped_players:
            foreign_id = scraped.get('foreign_id')
            if not foreign_id:
                logger.warning(
                    f"Pomijam zawodnika bez foreign_id: "
                    f"{scraped.get('first_name')} {scraped.get('last_name')}"
                )
                continue
            scraped_foreign_ids.add(foreign_id)

            resolved_player_id = already_resolved.get(foreign_id)
            if resolved_player_id is not None:
                # Już dopasowany wcześniej (np. przy okazji innej drużyny) —
                # jeśli od tamtej pory zmienił drużynę, uaktualnij przypisanie.
                player = player_manager.get_player_by_id(resolved_player_id)
                if player and player.team_id != team.id:
                    player_manager.update_player(player.id, team_id=team.id)
                continue

            best_player, score = _best_match(scraped['first_name'], scraped['last_name'], all_players)
            PendingPlayerMatch.upsert(
                team_id=team.id,
                scraper_id=scraper_id,
                scraped_first_name=scraped['first_name'],
                scraped_last_name=scraped['last_name'],
                scraped_foreign_id=foreign_id,
                scraped_is_goalkeeper=bool(scraped.get('is_goalkeeper')),
                suggested_player_id=best_player.id if best_player else None,
                similarity_score=score,
            )
            new_matches += 1

        departed_player_ids = []
        for player in Player.query.filter_by(team_id=team.id).all():
            foreign_id = player.get_foreign_id(scraper_id)
            if foreign_id and foreign_id not in scraped_foreign_ids:
                departed_player_ids.append(player.id)
        PendingPlayerDeparture.sync(team.id, scraper_id, departed_player_ids)

        return {'new_matches': new_matches, 'departed': len(departed_player_ids)}

    def get_pending_player_matches(self, team_id: int) -> List[PendingPlayerMatch]:
        return PendingPlayerMatch.get_for_team(team_id)

    def resolve_pending_player_match(self, pending_id: int, existing_player_id: Optional[int] = None,
                                      first_name: Optional[str] = None, last_name: Optional[str] = None,
                                      number: Optional[int] = None) -> Player:
        """
        Zatwierdź kandydata: połącz z istniejącym zawodnikiem (existing_player_id,
        przenosząc go do tej drużyny jeśli był przypisany gdzie indziej) albo
        utwórz nowego (first_name/last_name — domyślnie ze scrapowanych danych,
        is_goalkeeper ze scrapowanej pozycji).
        """
        pending = PendingPlayerMatch.query.get(pending_id)
        if not pending:
            raise ValueError("Nie znaleziono wpisu do zatwierdzenia")

        if existing_player_id:
            player = player_manager.get_player_by_id(existing_player_id)
            if not player:
                raise ValueError("Nie znaleziono wskazanego zawodnika")
            if player.team_id != pending.team_id:
                player_manager.update_player(player.id, team_id=pending.team_id)
        else:
            fn = first_name or pending.scraped_first_name
            ln = last_name or pending.scraped_last_name
            if not fn or not ln:
                raise ValueError("Nowy zawodnik wymaga podania imienia i nazwiska")
            player = player_manager.create_player(
                first_name=fn, last_name=ln, team_id=pending.team_id,
                number=number, is_goalkeeper=pending.scraped_is_goalkeeper,
            )

        player_manager.set_player_foreign_id(player.id, pending.scraper_id, pending.scraped_foreign_id)

        db.session.delete(pending)
        db.session.commit()
        return player

    def reject_pending_player_match(self, pending_id: int) -> bool:
        pending = PendingPlayerMatch.query.get(pending_id)
        if not pending:
            return False
        db.session.delete(pending)
        db.session.commit()
        return True

    def resolve_all_suggested_player_matches(self, team_id: int) -> Dict[str, int]:
        """
        „Potwierdź wszystkie": automatycznie zatwierdź wpisy oczekujące, które
        mają sugerowanego zawodnika (similarity >= SIMILARITY_THRESHOLD).
        Wpisy bez sugestii (nowy zawodnik) wymagają ręcznej decyzji i zostają
        w kolejce.
        """
        confirmed, skipped = 0, 0
        for pending in PendingPlayerMatch.get_for_team(team_id):
            if not pending.suggested_player_id:
                skipped += 1
                continue
            try:
                self.resolve_pending_player_match(pending.id, existing_player_id=pending.suggested_player_id)
                confirmed += 1
            except ValueError:
                skipped += 1
        return {'confirmed': confirmed, 'skipped': skipped}

    # =========================
    # Odejścia z drużyny (zawodnicy zniknięci z kadry na www)
    # =========================

    def get_pending_player_departures(self, team_id: int) -> List[PendingPlayerDeparture]:
        return PendingPlayerDeparture.get_for_team(team_id)

    def confirm_pending_player_departure(self, pending_id: int) -> Player:
        """Potwierdź odejście: wyzeruj team_id zawodnika (zostaje wolnym agentem)."""
        pending = PendingPlayerDeparture.query.get(pending_id)
        if not pending:
            raise ValueError("Nie znaleziono wpisu do potwierdzenia")

        player = player_manager.remove_player_from_team(pending.player_id)
        db.session.delete(pending)
        db.session.commit()
        return player

    def dismiss_pending_player_departure(self, pending_id: int) -> bool:
        """Odrzuć alarm o odejściu — zawodnik zostaje w drużynie bez zmian.
        Jeśli nadal będzie nieobecny w kolejnym scrapowaniu, zostanie zgłoszony ponownie."""
        pending = PendingPlayerDeparture.query.get(pending_id)
        if not pending:
            return False
        db.session.delete(pending)
        db.session.commit()
        return True
