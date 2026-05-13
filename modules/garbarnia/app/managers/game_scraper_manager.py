"""Game Scraper Manager — MZPN IV liga małopolska

Analogiczna struktura do modules/futsal_nalf/app/managers/game_scraper_manager.py.

Różnice względem futsal:
  - brak foreign_id meczu (strona MZPN nie daje UUID per mecz)
    → identyfikacja po: league_id + round + home_team_id + away_team_id
  - brak periods w futsalu przy scrapowaniu — tutaj tworzymy od razu 2 połowy
    z bramkami z przerwy pobranymi z WWW
  - dopasowanie drużyn: case-insensitive (MZPN używa WIELKICH LITER)
    futsal: po nazwie z bazy; tutaj: normalizacja → lowercase + jeden spacja
"""
import re
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

from flask import current_app
from core.extensions import db

logger = logging.getLogger(__name__)


def _normalize(name: str) -> str:
    """Normalizuj nazwę drużyny: lowercase, jeden spacja."""
    return re.sub(r'\s+', ' ', name.lower().strip())


class GameScraperManager:
    """Manager scrapowania terminarza MZPN — wątek w tle, status, zapis do bazy."""

    def __init__(self):
        self._scraping_thread: Optional[threading.Thread] = None
        self._scraping_lock = threading.Lock()
        self._status: Dict = {
            'status':        'idle',
            'total_scraped': 0,
            'updated':       0,
            'new_pending':   0,
            'error':         None,
        }

    # ── Publiczne API ─────────────────────────────────────────────────────────

    def scrape_games_async(self, league_urls: List[str], league_name: str = '') -> bool:
        """
        Uruchom scrapowanie w wątku w tle.

        Args:
            league_urls: Lista URL-i terminarzy
            league_name: Czytelna nazwa ligi (do socketio emit)

        Returns:
            True jeśli wątek wystartował, False jeśli już działa
        """
        with self._scraping_lock:
            if self._scraping_thread and self._scraping_thread.is_alive():
                logger.warning("Scrapowanie już trwa")
                return False

            self._status = {
                'status':        'in_progress',
                'total_scraped': 0,
                'updated':       0,
                'new_pending':   0,
                'error':         None,
            }

            app = current_app._get_current_object()
            self._scraping_thread = threading.Thread(
                target=self._scrape_worker,
                args=(app, league_urls, league_name),
                daemon=True,
            )
            self._scraping_thread.start()

            from core.extensions import socketio
            socketio.emit('scraping_started', {'name': league_name})
            logger.info(f"Scrapowanie uruchomione w tle: {len(league_urls)} URL(i)")
            return True

    def get_scraping_status(self) -> Dict:
        """Zwróć aktualny status scrapowania."""
        return self._status.copy()

    def clear_scraping_status(self):
        """Zresetuj status do 'idle'."""
        self._status = {
            'status': 'idle', 'total_scraped': 0,
            'updated': 0, 'new_pending': 0, 'error': None,
        }

    def is_scraping_in_progress(self) -> bool:
        return self._status['status'] == 'in_progress'

    # ── Wątek roboczy ─────────────────────────────────────────────────────────

    def _scrape_worker(self, app, league_urls: List[str], league_name: str):
        """Wątek w tle — pobiera HTML, przetwarza, zapisuje do bazy."""
        with app.app_context():
            from core.extensions import socketio
            try:
                from app.managers.scrapers.game_scraper import GameScraper
                scraper      = GameScraper()
                scraped_games = scraper.scrape_multiple_leagues(league_urls)
                stats        = self._process_scraped_games(scraped_games)

                self._status = {
                    'status':        'completed',
                    'total_scraped': stats['total_scraped'],
                    'updated':       stats['updated'],
                    'new_pending':   stats['new_pending'],
                    'error':         None,
                }
                logger.info(
                    f"Scrapowanie zakończone: {stats['total_scraped']} łącznie, "
                    f"{stats['updated']} zaktualizowanych, {stats['new_pending']} nowych"
                )
                socketio.emit('scraping_completed', {
                    'status':        'success',
                    'name':          league_name,
                    'total_scraped': stats['total_scraped'],
                    'updated':       stats['updated'],
                    'new_pending':   stats['new_pending'],
                })

            except Exception as e:
                logger.error(f"Błąd scrapowania w wątku: {e}", exc_info=True)
                self._status = {
                    'status': 'error', 'total_scraped': 0,
                    'updated': 0, 'new_pending': 0, 'error': str(e),
                }
                socketio.emit('scraping_error', {
                    'status': 'error', 'name': league_name, 'error': str(e),
                })

    # ── Przetwarzanie i zapis do bazy ─────────────────────────────────────────

    def _process_scraped_games(self, scraped_games: List[Dict]) -> Dict[str, int]:
        """
        Przetworz listę meczów z scrapera i zapisz do bazy.

        Identyfikacja istniejącego meczu: league_id + round + home_team_id + away_team_id.
        (MZPN nie daje foreign_id per mecz — inaczej niż futsal.)

        Logika aktualizacji:
          - Jeśli WWW mówi STATUS_NOT_STARTED ale DB ma bardziej zaawansowany status
            (np. mecz właśnie trwa lub skończył się) → pomijamy, DB jest aktualniejsza.
          - W przeciwnym razie aktualizujemy zmienione pola.

        Dla nowych meczów tworzy też 2 okresy (1. i 2. połowa).
        """
        from app.models.game   import Game
        from app.models.period import Period
        from app.models.league       import League

        # Buduj słownik drużyn z aktualnej ligi/sezonu raz dla całego batcha
        team_lookup = self._build_team_lookup()
        if not team_lookup:
            logger.error("Brak drużyn w bazie — przerywam import")
            return {'total_scraped': len(scraped_games), 'updated': 0, 'new_pending': 0}

        # Pobierz league_id (zakładamy jedną ligę skonfigurowaną w Settings)
        league_id = self._get_current_league_id()
        if not league_id:
            logger.error("Nie można ustalić league_id — przerywam import")
            return {'total_scraped': len(scraped_games), 'updated': 0, 'new_pending': 0}

        updated_count  = 0
        new_count      = 0
        STATUS_NOT_STARTED = Game.STATUS_NOT_STARTED
        STATUS_FINISHED    = Game.STATUS_FINISHED

        for gd in scraped_games:
            home_team = team_lookup.get(_normalize(gd['home_team_name']))
            away_team = team_lookup.get(_normalize(gd['away_team_name']))

            if not home_team or not away_team:
                logger.warning(
                    f"Pomijam kolejka={gd['round']} "
                    f"'{gd['home_team_name']}' vs '{gd['away_team_name']}' — brak drużyny w bazie"
                )
                continue

            status          = gd['status']
            home_goals      = gd['home_team_goals']
            away_goals      = gd['away_team_goals']
            parsed_date     = self._parse_date(gd['date'])

            # ── Szukaj istniejącego meczu ─────────────────────────────────
            existing = Game.query.filter_by(
                league_id    = league_id,
                round        = gd['round'],
                home_team_id = home_team.id,
                away_team_id = away_team.id,
            ).first()

            if existing:
                # DB jest aktualniejsza jeśli mecz trwa lub się skończył
                www_not_started = (status == STATUS_NOT_STARTED)
                db_more_advanced = (existing.status != STATUS_NOT_STARTED)
                if www_not_started and db_more_advanced:
                    logger.debug(
                        f"Pomijam kolejka={gd['round']} "
                        f"{gd['home_team_name']} vs {gd['away_team_name']} "
                        f"— www=NOT_STARTED, db={existing.status}"
                    )
                    continue

                changes = {
                    'home_team_goals': (existing.home_team_goals, home_goals),
                    'away_team_goals': (existing.away_team_goals, away_goals),
                    'status':          (existing.status,          status),
                    'date':            (existing.date,            parsed_date),
                }
                changed = [f for f, (old, new) in changes.items() if old != new]
                if changed:
                    for field in changed:
                        setattr(existing, field, changes[field][1])
                    existing.updated_at = datetime.utcnow()
                    logger.info(f"Zaktualizowano mecz id={existing.id}: {changed}")
                    # Zaktualizuj też okresy
                    self._upsert_periods(existing, gd, Period)
                    updated_count += 1

            else:
                # Nowy mecz
                game = Game(
                    league_id       = league_id,
                    round           = gd['round'],
                    group_nr        = 1,
                    home_team_id    = home_team.id,
                    away_team_id    = away_team.id,
                    stadium_id      = 1,
                    date            = parsed_date,
                    status          = status,
                    home_team_goals = home_goals,
                    away_team_goals = away_goals,
                )
                db.session.add(game)
                db.session.flush()   # game.id dostępne przed commit
                game.home_team_short_name = home_team.short_name
                game.away_team_short_name = away_team.short_name
                self._upsert_periods(game, gd, Period)
                logger.info(
                    f"Nowy mecz kolejka={gd['round']} "
                    f"{gd['home_team_name']} vs {gd['away_team_name']}"
                )
                new_count += 1

        db.session.commit()
        return {
            'total_scraped': len(scraped_games),
            'updated':       updated_count,
            'new_pending':   new_count,
        }

    # ── Okresy ───────────────────────────────────────────────────────────────

    @staticmethod
    def _upsert_periods(game, gd: Dict, Period):
        """
        Utwórz lub zaktualizuj dwa okresy (1. i 2. połowa) dla meczu.

        Bramki 2. połowy = bramki końcowe − bramki do przerwy.
        """
        STATUS_FINISHED    = Period.STATUS_FINISHED
        STATUS_NOT_STARTED = Period.STATUS_NOT_STARTED
        
        is_finished = (gd['status'] == STATUS_FINISHED)
        home_ht     = gd['home_ht_goals'] or 0
        away_ht     = gd['away_ht_goals'] or 0
        home_2h     = ((gd['home_team_goals'] or 0) - home_ht) if is_finished else 0
        away_2h     = ((gd['away_team_goals'] or 0) - away_ht) if is_finished else 0



        periods_data = [
            {
                'period_order':  1,
                'description':   '1. połowa',
                'main_timer_name': f'{game.home_team.short_name}x{game.away_team.short_name} p:1',
                'limit':         2700000,    # 45 min w ms
                'initial_time':  0,
                'home_goals':    home_ht if is_finished else 0,
                'away_goals':    away_ht if is_finished else 0,
                'status':        STATUS_FINISHED if is_finished else STATUS_NOT_STARTED,
            },
            {
                'period_order':  2,
                'description':   '2. połowa',
                'main_timer_name': f'{game.home_team.short_name}x{game.away_team.short_name} p:2',
                'limit':         2700000,
                'initial_time':  2700000,    # offset 45:00 dla overlay
                'home_goals':    home_2h,
                'away_goals':    away_2h,
                'status':        STATUS_FINISHED if is_finished else STATUS_NOT_STARTED,
            },
        ]

        for pd in periods_data:
            existing = Period.query.filter_by(
                game_id      = game.id,
                period_order = pd['period_order'],
            ).first()

            if existing:
                existing.home_team_goals = pd['home_goals']
                existing.away_team_goals = pd['away_goals']
                existing.status          = pd['status']
                existing.updated_at      = datetime.utcnow()
            else:
                period = Period(
                    game_id         = game.id,
                    period_order    = pd['period_order'],
                    description     = pd['description'],
                    limit           = pd['limit'],
                    main_timer_name    = pd['main_timer_name'],
                    initial_time    = pd['initial_time'],
                    pause_at_limit  = False,
                    home_team_goals = pd['home_goals'],
                    away_team_goals = pd['away_goals'],
                    status          = pd['status'],
                )
                db.session.add(period)

    # ── Helpery ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_team_lookup() -> Dict[str, object]:
        """
        Zbuduj słownik {normalized_name → Team} z drużyn bieżącej ligi/sezonu.
        Filtrowanie przez LeagueTeam → tylko drużyny z aktualnej ligi.
        """
        from app.models.settings import Settings
        from app.models.team import Team
        from app.models.league_team import LeagueTeam

        settings = Settings.get_settings()
        if not settings.current_game_id:
            # Fallback: wszystkie drużyny z bazy
            teams = Team.query.all()
        else:
            # Pobierz drużyny z ligi bieżącego meczu
            from app.models.game import Game
            game = Game.query.get(settings.current_game_id)
            if game:
                team_ids = (
                    db.session.query(LeagueTeam.team_id)
                    .filter_by(league_id=game.league_id)
                    .subquery()
                )
                teams = Team.query.filter(Team.id.in_(team_ids)).all()
            else:
                teams = Team.query.all()

        lookup = {_normalize(t.name): t for t in teams}
        logger.debug(f"Zbudowano lookup dla {len(lookup)} drużyn")
        return lookup

    @staticmethod
    def _get_current_league_id() -> Optional[int]:
        """Pobierz league_id z aktualnych ustawień lub pierwszej ligi w bazie."""
        from app.models.settings import Settings
        from app.models.game  import Game

        settings = Settings.get_settings()
        if settings.current_game_id:
            game = Game.query.get(settings.current_game_id)
            if game:
                return game.league_id

        # Fallback: pobierz z pierwszej dostępnej ligi
        from app.models.league import League
        league = League.query.first()
        return league.id if league else None

    @staticmethod
    def _parse_date(date_str: Optional[str]):
        """Parsuj 'YYYY-MM-DD HH:MM:SS+00:00' → datetime lub None."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S+00:00')
        except ValueError:
            return None