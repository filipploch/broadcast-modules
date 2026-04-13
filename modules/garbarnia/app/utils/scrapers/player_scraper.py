"""
player_scraper_laczynaspilka.py
Scraper zawodników drużyny z plików HTML pobranych z laczynaspilka.pl

Źródło: https://www.laczynaspilka.pl/rozgrywki/druzyna/{team_foreign_id}?tab=tab-zawodnicy
Pliki HTML zapisywane lokalnie przez Dockset lub ręczne pobranie.

Nazwa pliku musi zawierać foreign_id drużyny (UUID), np.:
    2026-04-12T11_58_24_..._803cdfe1-dc78-4ce9-b809-d5f8947aa876_tab_tab-zawodnicy...html

Struktura karty zawodnika w HTML:
    <app-pzpn-card-squad-member>
        <svg><title>jersey / game / 1</title>   ← bramkarz
        <svg><title>jersey / game / 2</title>   ← zawodnik z pola
        <div class="number"> 7 </div>
        <h3 class="card-squad-member__name">Jakub Bigosiński</h3>
        <a href=".../zawodnik/{player_foreign_id}">Zobacz profil</a>
    </app-pzpn-card-squad-member>
"""
import re
import logging
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# UUID pattern
_UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def find_html_file_for_team(html_dir: str | Path, team_foreign_id: str) -> Optional[Path]:
    """
    Znajdź plik HTML w katalogu który zawiera foreign_id drużyny w nazwie.

    Args:
        html_dir:        Katalog z pobranymi plikami HTML
        team_foreign_id: UUID drużyny (np. '803cdfe1-dc78-4ce9-b809-d5f8947aa876')

    Returns:
        Path do pliku lub None jeśli nie znaleziono
    """
    html_dir = Path(html_dir)
    if not html_dir.exists():
        logger.error(f"Katalog {html_dir} nie istnieje")
        return None

    for path in html_dir.glob('*.html'):
        if team_foreign_id in path.name:
            logger.debug(f"Znaleziono plik dla drużyny {team_foreign_id}: {path.name}")
            return path

    logger.warning(f"Nie znaleziono pliku HTML dla drużyny {team_foreign_id} w {html_dir}")
    return None


def scrape_players_from_html(html_path: str | Path, team_foreign_id: str) -> list[dict]:
    """
    Pobierz dane zawodników z pliku HTML.

    Args:
        html_path: Ścieżka do pliku HTML

    Returns:
        Lista słowników z danymi zawodników:
        [
            {
                'first_name':    str,
                'last_name':     str,
                'number':        int | None,   # None jeśli nie grał w ostatnim meczu
                'is_goalkeeper': bool,
                'foreign_id':    str | None,   # UUID zawodnika
            },
            ...
        ]
    """
    html_path = Path(html_path)
    with open(html_path, encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    players = []

    for card in soup.select('app-pzpn-card-squad-member'):
        # ── Imię i nazwisko ──────────────────────────────────────────────────
        name_el = card.select_one('.card-squad-member__name')
        if not name_el:
            continue
        full_name  = name_el.text.strip()
        parts      = full_name.split(' ', 1)
        first_name = parts[0]
        last_name  = parts[1] if len(parts) > 1 else ''

        # ── Numer koszulki ───────────────────────────────────────────────────
        # Strona wyświetla numer z ostatniego meczu — może być pusty
        number_el  = card.select_one('.number')
        number_raw = number_el.text.strip() if number_el else ''
        number     = int(number_raw) if number_raw.isdigit() else None

        # ── Bramkarz ─────────────────────────────────────────────────────────
        # jersey / game / 1 = bramkarz (jeden prostokąt na koszulce)
        # jersey / game / 2 = zawodnik z pola (dwa prostokąty)
        jersey_title = card.select_one('svg title')
        jersey_text  = jersey_title.text.strip() if jersey_title else ''
        is_goalkeeper = (jersey_text == 'jersey / game / 1')

        # ── Foreign ID ───────────────────────────────────────────────────────
        # href="https://www.laczynaspilka.pl/rozgrywki/zawodnik/{UUID}"
        link_el    = card.select_one('.card-squad-member__link a')
        href       = link_el.get('href', '') if link_el else ''
        fid_match  = re.search(r'/zawodnik/(' + _UUID_RE.pattern + r')', href)
        foreign_id = fid_match.group(1) if fid_match else None

        players.append({
            'first_name':    first_name,
            'last_name':     last_name,
            'number':        number,
            'is_goalkeeper': is_goalkeeper,
            'foreign_id':    foreign_id,
                'team_foreign_id': team_foreign_id,
        })

    logger.info(f"Sparsowano {len(players)} zawodników z {html_path.name}")
    return players


def scrape_players_for_team(html_dir: str | Path, team_foreign_id: str) -> list[dict]:
    """
    Główna funkcja: znajdź plik HTML dla drużyny i pobierz z niego zawodników.

    Args:
        html_dir:        Katalog z plikami HTML
        team_foreign_id: UUID drużyny

    Returns:
        Lista słowników z danymi zawodników (pusta jeśli pliku nie ma)
    """
    html_path = find_html_file_for_team(html_dir, team_foreign_id)
    if not html_path:
        return []
    return scrape_players_from_html(html_path, team_foreign_id)