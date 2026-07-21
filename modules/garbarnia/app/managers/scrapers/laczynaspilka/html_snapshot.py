"""Wspólna obsługa lokalnie zapisanych snapshotów HTML (np. wtyczką SingleFile)
dla scraperów laczynaspilka — zarówno kadry drużyny (player_scraper), jak i
tabeli rozgrywek (team_scraper).
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_latest_matching_html(html_dir: str | Path, marker: str) -> Optional[Path]:
    """
    Znajdź w katalogu najnowszy plik *.html, którego nazwa zawiera `marker`,
    usuwając po drodze starsze pasujące wersje.

    Admin potrafi zapisać nowszą wersję strony (np. po zmianie sezonu), nie
    usuwając poprzedniej — jeśli scraper nie zdąży przetworzyć starej wersji
    przed kolejnym zapisem, w katalogu zostają dwie (albo więcej) wersje tego
    samego dokumentu. Zanim dojdzie do odczytu, usuwamy wszystkie wersje
    starsze niż najnowsza (po czasie modyfikacji pliku), żeby scraper zawsze
    operował na jednym, aktualnym pliku — inaczej mógłby losowo trafić na
    przestarzałe dane w zależności od kolejności zwracanej przez glob().

    Args:
        html_dir: Katalog z zapisanymi plikami HTML
        marker:   Fragment nazwy pliku identyfikujący dokument (UUID drużyny
                  dla kadry, 'season' dla tabeli rozgrywek)

    Returns:
        Path do najnowszego pasującego pliku, albo None jeśli żaden nie pasuje.
    """
    html_dir = Path(html_dir)
    if not html_dir.exists():
        logger.error(f"Katalog {html_dir} nie istnieje")
        return None

    matches = sorted(
        (p for p in html_dir.glob('*.html') if marker in p.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        logger.warning(f"Nie znaleziono pliku HTML zawierającego '{marker}' w {html_dir}")
        return None

    latest, *older = matches
    for stale in older:
        logger.info(f"Usuwam starszą wersję zapisanego pliku: {stale.name} (nowsza: {latest.name})")
        stale.unlink(missing_ok=True)

    logger.debug(f"Znaleziono najnowszy plik pasujący do '{marker}': {latest.name}")
    return latest
