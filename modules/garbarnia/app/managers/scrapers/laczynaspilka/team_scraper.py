"""Laczynaspilka Team Scraper — wyciąga unikalne drużyny z lokalnie zapisanej
strony tabeli rozgrywek (np. .../rozgrywki?season=...&leagueGroup=...&leagueId=...).

W przeciwieństwie do strony pojedynczej drużyny (zakładka zawodnicy), strona
tabeli nie eksponuje w statycznym HTML żadnego stabilnego ID drużyny — UUID
widoczny jest dopiero w URL profilu drużyny, a ten UUID zmienia się przy
każdej zmianie sezonu (stąd w ogóle potrzeba tego scrapera: żeby co sezon
na nowo dopasować drużyny z www do rekordów Team w bazie). Jedynym stabilnym
identyfikatorem na tej stronie jest nazwa drużyny — analogicznie do
malopolskizpn, foreign_id = nazwa dokładnie jak wyświetlona na www.

Plik HTML znajdowany jest po nazwie zawierającej 'season' (tak zapisuje go
admin, np. wtyczką SingleFile, przed scrapowaniem) — tak jak PlayerScraper
znajduje plik drużyny po UUID w nazwie pliku.
"""
import logging
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from app.managers.scrapers.laczynaspilka.html_snapshot import find_latest_matching_html

logger = logging.getLogger(__name__)


class LaczynaspilkaTeamScraper:
    """Scraper drużyn z lokalnie zapisanej strony tabeli rozgrywek laczynaspilka.pl."""

    @staticmethod
    def find_html_file(html_dir: str | Path) -> Optional[Path]:
        """Znajdź najnowszy plik HTML w katalogu, którego nazwa zawiera 'season'
        — usuwając po drodze starsze zapisane wersje tej samej strony."""
        return find_latest_matching_html(html_dir, 'season')

    @staticmethod
    def scrape_teams_from_html(html_path: str | Path) -> list[dict]:
        """
        Pobierz unikalne nazwy drużyn z zapisanej strony tabeli rozgrywek.

        Strona potrafi zawierać kilka tabel (ogólna / u siebie / na wyjeździe)
        z tym samym kompletem drużyn w różnej kolejności — stąd deduplikacja
        po nazwie, z zachowaniem kolejności pierwszego wystąpienia.
        """
        html_path = Path(html_path)
        with open(html_path, encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        teams: dict[str, dict] = {}
        for name_el in soup.select('.squad-name__name--full'):
            name = name_el.text.strip()
            if name and name not in teams:
                teams[name] = {'name': name, 'foreign_id': name}

        result = list(teams.values())
        logger.info(f"Sparsowano {len(result)} unikalnych drużyn z {html_path.name}")
        return result
