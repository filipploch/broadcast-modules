"""MZPN Game Scraper — scraping terminarza/wyników z malopolskizpn.pl

Analogiczna struktura do modules/futsal_nalf/app/managers/scrapers/nalffutsal/game_scraper.py.

URL terminarza: https://malopolskizpn.pl/rozgrywki/2025-2026/seniorzy/iv_liga/?view=schedule

Struktura HTML:
    <div class="mzpn-schedule">
        <div class="mzpn-round-title">Kolejka 1</div>
        <div class="mzpn-match">
            <div class="dt">
                <span class="d">9.08.2025</span>
                <span class="t"> 11:00</span>
            </div>
            <div class="teams">
                <span class="h">GARBARNIA KRAKÓW</span>
                <span class="s">2:0 (1:0)</span>   ← pusty string = brak wyniku
                <span class="g">OKOCIMSKI KLUB SPORTOWY BRZESKO</span>
            </div>
        </div>
        ...
        <div class="mzpn-round-title">Kolejka 2</div>
        ...
    </div>

Każdy mecz zwracany jako słownik z kluczami:
    foreign_id            str | None  '{GOSPODARZ}vs{GOŚĆ}at{league_id}' — tylko
                                       gdy league_id podany do scrape_game()/
                                       scrape_multiple_leagues() (patrz niżej)
    round                 int
    date                  str  'YYYY-MM-DD HH:MM:SS'  (lub None)
    home_team_name        str  oryginalna nazwa z WWW (uppercase)
    away_team_name        str
    home_team_foreign_id  str  == home_team_name (MZPN: foreign_id drużyny to jej nazwa)
    away_team_foreign_id  str  == away_team_name
    home_team_goals       int | None
    away_team_goals       int | None
    home_ht_goals         int | None   bramki 1. połowy gospod.
    away_ht_goals         int | None   bramki 1. połowy gości
    status                int  Game.STATUS_FINISHED(2) | Game.STATUS_NOT_STARTED(0)

foreign_id meczu — MZPN nie daje żadnego ID per mecz w HTML (data/wynik mogą
się zmienić między scrapowaniami), jedyne stałe dane to nazwy drużyn. W obrębie
jednej ligi/sezonu (czyli jednego league_id w naszej bazie) para (gospodarz,
gość) nie powtarza się — różne rozgrywki (liga/puchar) i różne sezony to zawsze
różne league_id — więc "{gospodarz}vs{gość}at{league_id}" jest unikalne i
deterministyczne bez potrzeby dodatkowego scrapowania.
"""
import re
import logging
import requests
from typing import Optional
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

_SCORE_RE = re.compile(r'(\d+):(\d+)\s*\((\d+):(\d+)\)')
_DATE_RE  = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')
_TIME_RE  = re.compile(r'(\d{1,2}):(\d{2})')

# Status constants — kopie z modelu Game (unikamy importu modelu tutaj)
STATUS_NOT_STARTED = 0
STATUS_FINISHED    = 2


class GameScraper:
    """Scraper terminarza MZPN IV ligi małopolskiej."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; broadcast-scraper/1.0)'
        })

    # ── Publiczne API (identyczne z futsal GameScraper) ───────────────────────

    def scrape_game(self, page_url: str, league_id: Optional[int] = None) -> list[dict]:
        """
        Pobierz i sparsuj terminarz z podanego URL.

        Args:
            page_url:  URL strony z terminarzem (np. .../iv_liga/?view=schedule)
            league_id: id ligi w naszej bazie — wstrzykiwane do foreign_id meczu
                       (patrz _build_match_foreign_id). Bez tego (np. gdy wywołuje
                       to team-scraper, który nie zna jeszcze league_id albo mu on
                       niepotrzebny) foreign_id meczu wychodzi None — wciąż da się
                       wyciągnąć same nazwy drużyn.

        Returns:
            Lista słowników z danymi meczów
        """
        try:
            response = self.session.get(page_url, timeout=15)
            response.raise_for_status()
            return self._parse_html(response.text, league_id)
        except requests.RequestException as e:
            logger.error(f"Błąd pobierania {page_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd scrapowania {page_url}: {e}", exc_info=True)
            return []

    def scrape_multiple_leagues(self, page_urls: list[str], league_id: Optional[int] = None) -> list[dict]:
        """
        Scrapuj wiele URL-i i zwróć połączoną listę meczów.

        Analogia do futsal GameScraper.scrape_multiple_leagues().

        Args:
            page_urls: Lista URL-i terminarzy
            league_id: patrz scrape_game() — współdzielone przez wszystkie URL-e
                       w tym wywołaniu (w praktyce zawsze wywoływane z jednym
                       URL-em na ligę)

        Returns:
            Połączona lista słowników z danymi meczów
        """
        all_games = []
        for url in page_urls:
            games = self.scrape_game(url, league_id)
            all_games.extend(games)
            logger.info(f"Scrapowano {len(games)} meczów z {url}")
        return all_games

    # ── Parsowanie HTML ───────────────────────────────────────────────────────

    def _parse_html(self, html: str, league_id: Optional[int] = None) -> list[dict]:
        """Parsuj HTML terminarza, zwróć listę meczów."""
        soup     = BeautifulSoup(html, 'html.parser')
        schedule = soup.select_one('.mzpn-schedule')
        if not schedule:
            logger.error("Nie znaleziono elementu .mzpn-schedule")
            return []

        games         = []
        current_round = None

        for element in schedule.children:
            if not element.name:
                continue
            classes = element.get('class') or []

            # ── Numer kolejki ─────────────────────────────────────────────
            if 'mzpn-round-title' in classes:
                m = re.search(r'\d+', element.text)
                current_round = int(m.group()) if m else None
                continue

            # ── Mecz ──────────────────────────────────────────────────────
            if 'mzpn-match' not in classes:
                continue
            if current_round is None:
                logger.warning("Mecz poza blokiem kolejki — pomijam")
                continue

            game_data = self._extract_game_data(element, current_round, league_id)
            if game_data:
                games.append(game_data)

        logger.info(f"Sparsowano {len(games)} meczów")
        return games

    def _extract_game_data(self, element, round_nr: int, league_id: Optional[int] = None) -> Optional[dict]:
        """
        Wyciągnij dane jednego meczu z elementu <div class="mzpn-match">.

        Returns:
            Słownik z danymi lub None jeśli brak wymaganych pól
        """
        try:
            date_el  = element.select_one('.d')
            time_el  = element.select_one('.t')
            home_el  = element.select_one('.h')
            away_el  = element.select_one('.g')
            score_el = element.select_one('.s')

            # Drużyny są wymagane — bez nich mecz jest bezużyteczny
            home_raw = re.sub(r'\s+', ' ', home_el.text.strip()) if home_el else None
            away_raw = re.sub(r'\s+', ' ', away_el.text.strip()) if away_el else None
            if not home_raw or not away_raw:
                logger.warning(f"Brak nazwy drużyny w kolejce {round_nr} — pomijam")
                return None

            date_str   = date_el.text.strip() if date_el else ''
            time_str   = time_el.text.strip() if time_el else ''
            score_text = score_el.text.strip() if score_el else ''

            score  = self._parse_score(score_text)
            dt_str = self._parse_datetime_str(date_str, time_str)

            return {
                # MZPN nie ma żadnego ID per mecz w HTML (data/wynik mogą się
                # zmienić) — jedyne stałe dane to nazwy drużyn. W obrębie jednej
                # ligi/sezonu (czyli jednego league_id w naszej bazie) para
                # (gospodarz, gość) nie powtarza się, więc to wystarcza za id.
                'foreign_id':           (
                    self._build_match_foreign_id(home_raw, away_raw, league_id)
                    if league_id is not None else None
                ),
                'round':                round_nr,
                'date':                 dt_str,
                'home_team_name':       home_raw,
                'away_team_name':       away_raw,
                # Foreign_id drużyny MZPN to jej nazwa (ustalone przy team-scraperze) —
                # więc tu po prostu ta sama wartość co home/away_team_name.
                'home_team_foreign_id': home_raw,
                'away_team_foreign_id': away_raw,
                'home_team_goals':      score['home_goals'],
                'away_team_goals':      score['away_goals'],
                'home_ht_goals':        score['home_ht_goals'],
                'away_ht_goals':        score['away_ht_goals'],
                'status':               score['status'],
            }
        except Exception as e:
            logger.error(f"Błąd parsowania meczu kolejka={round_nr}: {e}")
            return None

    # ── Pomocnicze ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_match_foreign_id(home_name: str, away_name: str, league_id: int) -> str:
        """'{GOSPODARZ}vs{GOŚĆ}at{league_id}' — unikalne w obrębie jednej ligi/
        sezonu: ta sama para nie powtarza się w danych rozgrywkach, a różne
        rozgrywki (liga/puchar) albo sezony to zawsze różne league_id."""
        return f'{home_name}vs{away_name}at{league_id}'

    @staticmethod
    def _parse_score(text: str) -> dict:
        """
        Parsuj wynik '2:0 (1:0)' → słownik z bramkami.
        Pusty string lub brak wzorca → None dla bramek, status NOT_STARTED.
        """
        empty = {
            'home_goals':    None,
            'away_goals':    None,
            'home_ht_goals': None,
            'away_ht_goals': None,
            'status':        STATUS_NOT_STARTED,
        }
        if not text:
            return empty
        m = _SCORE_RE.search(text)
        if not m:
            return empty
        return {
            'home_goals':    int(m.group(1)),
            'away_goals':    int(m.group(2)),
            'home_ht_goals': int(m.group(3)),
            'away_ht_goals': int(m.group(4)),
            'status':        STATUS_FINISHED,
        }

    @staticmethod
    def _parse_datetime_str(date_text: str, time_text: str) -> Optional[str]:
        """
        Połącz datę '9.08.2025' i czas '11:00' w string 'YYYY-MM-DD HH:MM:SS'.
        Zwraca None jeśli parsowanie się nie uda.
        """
        dm = _DATE_RE.search(date_text)
        tm = _TIME_RE.search(time_text)
        if not dm:
            return None
        day, month, year = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        hour   = int(tm.group(1)) if tm else 0
        minute = int(tm.group(2)) if tm else 0
        try:
            dt = datetime(year, month, day, hour, minute)
            return dt.strftime('%Y-%m-%d %H:%M:%S+00:00')
        except ValueError:
            return None