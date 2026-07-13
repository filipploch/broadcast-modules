"""Malopolski ZPN Team Scraper — wyciąga unikalne drużyny z terminarza (HTML)
malopolskizpn.pl.

Współdzieli fetch+parsing z GameScraper (ten sam URL terminarza i selektory
.h/.g), ale zamiast wyniku meczu interesują nas tylko nazwy drużyn.

MZPN nie udostępnia żadnego stabilnego ID per drużyna (w przeciwieństwie do
superscore, gdzie mamy slug/hash) — jedynym identyfikatorem jest nazwa
zapisana w HTML (WIELKIMI LITERAMI, np. "GARBARNIA KRAKÓW"), więc foreign_id
drużyny jest po prostu tą nazwą.
"""
import logging

from app.managers.scrapers.malopolskizpn.game_scraper import GameScraper

logger = logging.getLogger(__name__)


class MalopolskiZpnTeamScraper:
    """Scraper drużyn z terminarza (lista spotkań) malopolskizpn.pl."""

    def __init__(self):
        self._game_scraper = GameScraper()

    def scrape_teams(self, games_url: str) -> list[dict]:
        """
        Pobierz unikalne drużyny z terminarza.

        Args:
            games_url: URL terminarza (np. .../iv_liga/?view=schedule)

        Returns:
            Lista słowników {'name': str, 'foreign_id': str} — foreign_id jest
            identyczny z name (nazwa drużyny dokładnie tak jak na www).

        Raises:
            RuntimeError: terminarz nie zwrócił żadnych meczów (błąd sieciowy,
                niepoprawny URL albo zmieniona struktura strony) —
                sygnalizowane jawnie zamiast cichego zwrócenia pustej listy,
                żeby nie wyglądało to jak "wszystko już dopasowane".
        """
        games = self._game_scraper.scrape_game(games_url)
        if not games:
            raise RuntimeError(
                f"Terminarz pod '{games_url}' nie zwrócił żadnych meczów — "
                f"sprawdź URL i czy strona jest dostępna."
            )

        teams_by_name = {}
        for game in games:
            for name in (game.get('home_team_name'), game.get('away_team_name')):
                if name and name not in teams_by_name:
                    teams_by_name[name] = {'name': name, 'foreign_id': name}

        teams = list(teams_by_name.values())
        logger.info(f"Sparsowano {len(teams)} unikalnych drużyn z {len(games)} meczów (MZPN)")
        return teams
