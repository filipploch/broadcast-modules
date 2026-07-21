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
from app.managers.scrapers.malopolskizpn.team_scraper import MalopolskiZpnTeamScraper
from app.managers.scrapers.laczynaspilka.team_scraper import LaczynaspilkaTeamScraper

SIMILARITY_THRESHOLD = 0.6

team_manager = TeamManager()
league_manager = LeagueManager()


def _superscore_scraper_id() -> int:
    scraper = Scraper.get_by_folder('superscore')
    if not scraper:
        raise RuntimeError("Scraper 'superscore' nie jest zarejestrowany w tabeli scrapers")
    return scraper.id


def _malopolskizpn_scraper_id() -> int:
    scraper = Scraper.get_by_folder('malopolskizpn')
    if not scraper:
        raise RuntimeError("Scraper 'malopolskizpn' nie jest zarejestrowany w tabeli scrapers")
    return scraper.id


def _laczynaspilka_scraper_id() -> int:
    scraper = Scraper.get_by_folder('laczynaspilka')
    if not scraper:
        raise RuntimeError("Scraper 'laczynaspilka' nie jest zarejestrowany w tabeli scrapers")
    return scraper.id


def _normalize(name: str) -> str:
    return ' '.join(name.lower().split())


def _normalize_upper(name: str) -> str:
    return ' '.join(name.upper().split())


def _best_match(name: str, candidates: List[Team], normalize=_normalize):
    """Zwraca (Team|None, score) najbardziej podobnej drużyny wśród candidates.

    normalize dobiera się do konwencji nazewnictwa źródła: superscore zapisuje
    nazwy "normalnie" (lowercase-owalne 1:1), MZPN WIELKIMI LITERAMI — stąd
    osobny _normalize_upper zamiast jednego domyślnego lowercase dla obu.
    """
    norm_name = normalize(name)
    best_team = None
    best_score = 0.0
    for team in candidates:
        score = difflib.SequenceMatcher(None, norm_name, normalize(team.name)).ratio()
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

        Drużyna już dopasowana wcześniej (ma wpis w TeamForeignId dla tego
        scrapera) nie trafia ponownie do przeglądu, ale jeśli nie jest jeszcze
        przypisana do TEJ ligi (np. dopasowano ją wcześniej przy okazji innej
        ligi), zostaje do niej dopisana automatycznie — to już potwierdzony
        match, więc nie wymaga ponownej decyzji admina.

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
        try:
            scraped_teams = SuperscoreTeamScraper().scrape_teams(league.superscore_season_id)
        except RuntimeError as e:
            raise ValueError(str(e)) from e

        already_resolved = {
            row.foreign_id: row.team_id
            for row in TeamForeignId.query.filter_by(scraper_id=scraper_id).all()
        }
        all_teams = Team.query.order_by(Team.name).all()
        league_team_ids = {lt.team_id for lt in league.get_teams()}

        count = 0
        for scraped in scraped_teams:
            resolved_team_id = already_resolved.get(scraped['foreign_id'])
            if resolved_team_id is not None:
                if resolved_team_id not in league_team_ids:
                    league_manager.add_team_to_league(league.id, resolved_team_id, group_nr=1)
                    league_team_ids.add(resolved_team_id)
                continue  # już dopasowane w poprzednim uruchomieniu

            best_team, score = _best_match(scraped['name'], all_teams)
            PendingTeamMatch.upsert(
                league_id=league_id,
                scraper_id=scraper_id,
                scraped_name=scraped['name'],
                scraped_foreign_id=scraped['foreign_id'],
                scraped_short_name=scraped.get('short_code'),
                suggested_team_id=best_team.id if best_team else None,
                similarity_score=score,
            )
            count += 1

        return count

    def scrape_league_teams_from_malopolskizpn(self, league_id: int) -> int:
        """
        Pobierz drużyny ligi z terminarza malopolskizpn.pl (lista spotkań) i
        zapisz kandydatów do dopasowania w PendingTeamMatch. Ten sam URL co
        scraper meczów (games_url) — MZPN nie ma osobnego endpointu na drużyny,
        więc parsujemy terminarz i wyciągamy unikalne nazwy z .h/.g.

        foreign_id drużyny to jej nazwa dokładnie jak na www (WIELKIMI
        LITERAMI) — MZPN nie udostępnia żadnego innego stabilnego ID. Dopasowanie
        do drużyn w bazie porównuje po konwersji obu stron do wielkich liter
        (_best_match_upper), inaczej niż lowercase używany dla superscore.

        Nic nie zapisuje bezpośrednio do Team/LeagueTeam — wymaga potwierdzenia
        przez resolve_pending_team_match(). Drużyna już dopasowana wcześniej
        (ma wpis w TeamForeignId dla tego scrapera) i nieprzypisana jeszcze do
        TEJ ligi zostaje do niej dopisana automatycznie (tak jak przy superscore).

        Returns:
            Liczba wpisów oczekujących utworzonych/odświeżonych.

        Raises:
            ValueError: brak ligi, brak skonfigurowanego URL terminarza (Dane
                scrapera: Małopolski ZPN), albo błąd pobierania danych.
        """
        league = League.query.get(league_id)
        if not league:
            raise ValueError("Nie znaleziono ligi")

        scraper_id = _malopolskizpn_scraper_id()
        games_url = league.get_scraper_url(scraper_id, 'games_url')
        if not games_url:
            raise ValueError(
                "Liga nie ma skonfigurowanego URL terminarza (Dane scrapera: Małopolski ZPN)"
            )

        try:
            scraped_teams = MalopolskiZpnTeamScraper().scrape_teams(games_url)
        except RuntimeError as e:
            raise ValueError(str(e)) from e

        already_resolved = {
            row.foreign_id: row.team_id
            for row in TeamForeignId.query.filter_by(scraper_id=scraper_id).all()
        }
        all_teams = Team.query.order_by(Team.name).all()
        league_team_ids = {lt.team_id for lt in league.get_teams()}

        count = 0
        for scraped in scraped_teams:
            resolved_team_id = already_resolved.get(scraped['foreign_id'])
            if resolved_team_id is not None:
                if resolved_team_id not in league_team_ids:
                    league_manager.add_team_to_league(league.id, resolved_team_id, group_nr=1)
                    league_team_ids.add(resolved_team_id)
                continue  # już dopasowane w poprzednim uruchomieniu

            best_team, score = _best_match(scraped['name'], all_teams, normalize=_normalize_upper)
            PendingTeamMatch.upsert(
                league_id=league_id,
                scraper_id=scraper_id,
                scraped_name=scraped['name'],
                scraped_foreign_id=scraped['foreign_id'],
                scraped_short_name=None,
                suggested_team_id=best_team.id if best_team else None,
                similarity_score=score,
            )
            count += 1

        return count

    def scrape_league_teams_from_laczynaspilka(self, league_id: int) -> int:
        """
        Pobierz drużyny ligi z lokalnie zapisanej strony tabeli rozgrywek
        laczynaspilka.pl (nazwa pliku zawiera 'season' — admin zapisuje ją
        np. wtyczką SingleFile, tak jak przy scrapowaniu kadry) i zapisz
        kandydatów do dopasowania w PendingTeamMatch.

        Strona tabeli nie eksponuje UUID drużyny (widoczny dopiero na stronie
        pojedynczej drużyny, a ten zmienia się co sezon) — foreign_id to
        nazwa drużyny, tak jak przy malopolskizpn. Dzięki temu dopasowanie
        raz potwierdzone przez admina jest rozpoznawane automatycznie w
        kolejnych sezonach, mimo że UUID drużyny na www się zmienił.

        Nic nie zapisuje bezpośrednio do Team/LeagueTeam — wymaga
        potwierdzenia przez resolve_pending_team_match(). Drużyna już
        dopasowana wcześniej i nieprzypisana jeszcze do TEJ ligi zostaje do
        niej dopisana automatycznie (tak jak przy pozostałych scraperach).

        Returns:
            Liczba wpisów oczekujących utworzonych/odświeżonych.

        Raises:
            ValueError: brak ligi, brak zapisanego pliku strony sezonu w
                katalogu tymczasowym, albo plik nie zawiera żadnych drużyn.
        """
        import sys
        from flask import current_app

        league = League.query.get(league_id)
        if not league:
            raise ValueError("Nie znaleziono ligi")

        scraper_id = _laczynaspilka_scraper_id()
        temp_dir = sys.path[0] + current_app.config['TEMP_DIR']

        html_scraper = LaczynaspilkaTeamScraper()
        html_path = html_scraper.find_html_file(temp_dir)
        if not html_path:
            raise ValueError(
                f"Nie znaleziono zapisanego pliku strony sezonu (nazwa zawierająca "
                f"'season') w katalogu {temp_dir} — zapisz stronę tabeli rozgrywek "
                f"(np. wtyczką SingleFile) przed scrapowaniem."
            )

        try:
            scraped_teams = html_scraper.scrape_teams_from_html(html_path)
        except Exception as e:
            raise ValueError(f"Błąd parsowania pliku {html_path.name}: {e}") from e
        if not scraped_teams:
            raise ValueError(
                f"Plik {html_path.name} nie zawiera żadnych drużyn — sprawdź, czy "
                f"strona zapisała się poprawnie i czy struktura strony się nie zmieniła."
            )

        already_resolved = {
            row.foreign_id: row.team_id
            for row in TeamForeignId.query.filter_by(scraper_id=scraper_id).all()
        }
        all_teams = Team.query.order_by(Team.name).all()
        league_team_ids = {lt.team_id for lt in league.get_teams()}

        count = 0
        for scraped in scraped_teams:
            resolved_team_id = already_resolved.get(scraped['foreign_id'])
            if resolved_team_id is not None:
                if resolved_team_id not in league_team_ids:
                    league_manager.add_team_to_league(league.id, resolved_team_id, group_nr=1)
                    league_team_ids.add(resolved_team_id)
                continue  # już dopasowane w poprzednim uruchomieniu

            best_team, score = _best_match(scraped['name'], all_teams)
            PendingTeamMatch.upsert(
                league_id=league_id,
                scraper_id=scraper_id,
                scraped_name=scraped['name'],
                scraped_foreign_id=scraped['foreign_id'],
                scraped_short_name=None,
                suggested_team_id=best_team.id if best_team else None,
                similarity_score=score,
            )
            count += 1

        # Plik usuwany dopiero tutaj — po tym jak wszystkie drużyny trafiły
        # bezpiecznie do PendingTeamMatch/TeamForeignId, żeby przy błędzie w
        # trakcie przetwarzania źródłowy plik zostawał do ponownej próby.
        html_path.unlink(missing_ok=True)

        return count

    def get_pending_team_matches(self, league_id: int) -> List[PendingTeamMatch]:
        return PendingTeamMatch.get_for_league(league_id)

    def resolve_pending_team_match(self, pending_id: int, existing_team_id: Optional[int] = None,
                                   name_14: Optional[str] = None, short_name: Optional[str] = None,
                                   short_name_choice: Optional[str] = None) -> Team:
        """
        Zatwierdź kandydata: połącz z istniejącą drużyną (existing_team_id) albo
        utwórz nową (name_14 + short_name wymagane w tym wariancie). Dopisuje
        drużynę do ligi jeśli jeszcze w niej nie jest.

        Jeśli drużyna już ma w bazie short_name inny niż pobrany przez scraper
        (np. wpisany ręcznie albo ustawiony przez inny scraper), wymaga
        jednoznacznej decyzji przez short_name_choice ('existing' albo
        'scraped') zamiast domyślnie wybierać jedną z wartości.
        """
        pending = PendingTeamMatch.query.get(pending_id)
        if not pending:
            raise ValueError("Nie znaleziono wpisu do zatwierdzenia")

        if existing_team_id:
            team = team_manager.get_team_by_id(existing_team_id)
            if not team:
                raise ValueError("Nie znaleziono wskazanej drużyny")

            if (pending.scraped_short_name and team.short_name
                    and pending.scraped_short_name != team.short_name):
                if short_name_choice not in ('existing', 'scraped'):
                    raise ValueError(
                        f"Drużyna ma w bazie short_name '{team.short_name}', a scraper pobrał "
                        f"'{pending.scraped_short_name}' — wskaż, który zachować."
                    )
                if short_name_choice == 'scraped':
                    team.short_name = pending.scraped_short_name
                    db.session.commit()
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

    def resolve_all_suggested_team_matches(self, league_id: int) -> Dict[str, int]:
        """
        „Potwierdź wszystkie": automatycznie zatwierdź wpisy oczekujące, które
        mają sugerowaną drużynę (similarity >= SIMILARITY_THRESHOLD), łącząc
        z sugestią. Przy konflikcie short_name zachowuje wersję już zapisaną
        w bazie (short_name_choice='existing') zamiast milcząco ją nadpisywać.
        Wpisy bez sugestii (nowa drużyna) wymagają ręcznej decyzji i zostają
        w kolejce.
        """
        confirmed, skipped = 0, 0
        for pending in PendingTeamMatch.get_for_league(league_id):
            if not pending.suggested_team_id:
                skipped += 1
                continue
            try:
                self.resolve_pending_team_match(
                    pending.id, existing_team_id=pending.suggested_team_id,
                    short_name_choice='existing',
                )
                confirmed += 1
            except ValueError:
                skipped += 1
        return {'confirmed': confirmed, 'skipped': skipped}
