"""Team Scraper Manager - statistics for the team list page, plus the
scraper-drużyn-ligi workflow (scrape → dopasowanie kandydatów → ręczne
zatwierdzenie w PendingTeamMatch).

Scraper nigdy nie łączy automatycznie znalezionej na www drużyny z rekordem
Team w bazie — tylko proponuje najbardziej prawdopodobnego kandydata po
podobieństwie nazw. Wiąże to dopiero resolve_pending_team_match(), wywołane
z ekranu przeglądu po decyzji admina.
"""
import difflib
from typing import Dict, List, Optional

from core.extensions import db
from core.managers.team_manager import TeamManager
from core.managers.league_manager import LeagueManager
from app.models.team import Team
from app.models.league import League
from app.models.scraper import Scraper
from app.models.pending_team_match import PendingTeamMatch
from app.models.team_foreign_id import TeamForeignId
from app.managers.scrapers.superscore.superscore_team_scraper import SuperscoreTeamScraper

SIMILARITY_THRESHOLD = 0.6

team_manager = TeamManager()
league_manager = LeagueManager()


def _superscore_scraper_id() -> int:
    scraper = Scraper.get_by_folder('superscore')
    if not scraper:
        raise RuntimeError("Scraper 'superscore' nie jest zarejestrowany w tabeli scrapers")
    return scraper.id


def _normalize(name: str) -> str:
    return ' '.join(name.lower().split())


def _best_match(name: str, candidates: List[Team]):
    """Zwraca (Team|None, score) najbardziej podobnej drużyny wśród candidates."""
    norm_name = _normalize(name)
    best_team = None
    best_score = 0.0
    for team in candidates:
        score = difflib.SequenceMatcher(None, norm_name, _normalize(team.name)).ratio()
        if score > best_score:
            best_score = score
            best_team = team
    if best_score >= SIMILARITY_THRESHOLD:
        return best_team, best_score
    return None, best_score


class TeamScraperManager:
    """Statystyki drużyn + workflow scrapowania/dopasowywania drużyn ligi."""

    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about teams"""
        return {'total_teams': Team.query.count()}

    # =========================
    # Scrapowanie drużyn ligi
    # =========================

    def scrape_league_teams_from_superscore(self, league_id: int) -> int:
        """
        Pobierz drużyny ligi z superscore.live i zapisz kandydatów do
        dopasowania w PendingTeamMatch. Nic nie zapisuje bezpośrednio do Team/
        LeagueTeam — to wymaga potwierdzenia przez resolve_pending_team_match().

        Returns:
            Liczba wpisów oczekujących utworzonych/odświeżonych.

        Raises:
            ValueError: brak ligi albo brak skonfigurowanego superscore_season_id
        """
        league = League.query.get(league_id)
        if not league:
            raise ValueError("Nie znaleziono ligi")
        if not league.superscore_season_id:
            raise ValueError("Liga nie ma skonfigurowanego superscore_season_id (Dane scrapera: Superscore)")

        scraper_id = _superscore_scraper_id()
        scraped_teams = SuperscoreTeamScraper().scrape_teams(league.superscore_season_id)

        already_resolved = {
            row.foreign_id for row in TeamForeignId.query.filter_by(scraper_id=scraper_id).all()
        }
        all_teams = Team.query.order_by(Team.name).all()

        count = 0
        for scraped in scraped_teams:
            if scraped['foreign_id'] in already_resolved:
                continue  # już dopasowane w poprzednim uruchomieniu

            best_team, score = _best_match(scraped['name'], all_teams)
            PendingTeamMatch.upsert(
                league_id=league_id,
                scraper_id=scraper_id,
                scraped_name=scraped['name'],
                scraped_foreign_id=scraped['foreign_id'],
                suggested_team_id=best_team.id if best_team else None,
                similarity_score=score,
            )
            count += 1

        return count

    def get_pending_team_matches(self, league_id: int) -> List[PendingTeamMatch]:
        return PendingTeamMatch.get_for_league(league_id)

    def resolve_pending_team_match(self, pending_id: int, existing_team_id: Optional[int] = None,
                                   name_14: Optional[str] = None, short_name: Optional[str] = None) -> Team:
        """
        Zatwierdź kandydata: połącz z istniejącą drużyną (existing_team_id) albo
        utwórz nową (name_14 + short_name wymagane w tym wariancie). Dopisuje
        drużynę do ligi jeśli jeszcze w niej nie jest.
        """
        pending = PendingTeamMatch.query.get(pending_id)
        if not pending:
            raise ValueError("Nie znaleziono wpisu do zatwierdzenia")

        if existing_team_id:
            team = team_manager.get_team_by_id(existing_team_id)
            if not team:
                raise ValueError("Nie znaleziono wskazanej drużyny")
        else:
            if not name_14 or not short_name:
                raise ValueError("Nowa drużyna wymaga podania nazwy skróconej i skrótu 3-literowego")
            team = team_manager.create_team(name=pending.scraped_name, name_14=name_14, short_name=short_name)

        team_manager.set_team_foreign_id(team.id, pending.scraper_id, pending.scraped_foreign_id)

        league = league_manager.get_league_by_id(pending.league_id)
        if not any(lt.team_id == team.id for lt in league.get_teams()):
            league_manager.add_team_to_league(league.id, team.id, group_nr=1)

        db.session.delete(pending)
        db.session.commit()
        return team

    def reject_pending_team_match(self, pending_id: int) -> bool:
        pending = PendingTeamMatch.query.get(pending_id)
        if not pending:
            return False
        db.session.delete(pending)
        db.session.commit()
        return True
