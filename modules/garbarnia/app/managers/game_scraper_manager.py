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

    def scrape_games_async(self, league_urls: List[str], league_name: str = '', league_id: Optional[int] = None) -> bool:
        """
        Uruchom scrapowanie MZPN (HTML) w wątku w tle.

        Args:
            league_urls: Lista URL-i terminarzy
            league_name: Czytelna nazwa ligi (do socketio emit)
            league_id:   id ligi w naszej bazie — wstrzykiwane do foreign_id
                         meczu (MZPN nie ma własnego ID per mecz, patrz
                         GameScraper._build_match_foreign_id)

        Returns:
            True jeśli wątek wystartował, False jeśli już działa
        """
        return self._start_scraping_thread(
            target=self._scrape_worker,
            args=(current_app._get_current_object(), league_urls, league_name, league_id),
            league_name=league_name,
        )

    def scrape_superscore_async(self, season_ids: List[str], league_name: str = '') -> bool:
        """
        Uruchom scrapowanie z superscore.live API w wątku w tle.

        Args:
            season_ids:  Lista ID sezonów (np. ['4vDT5gZAVMkCxWuCYl8kzc'])
            league_name: Czytelna nazwa ligi (do socketio emit)

        Returns:
            True jeśli wątek wystartował, False jeśli już działa
        """
        return self._start_scraping_thread(
            target=self._scrape_superscore_worker,
            args=(current_app._get_current_object(), season_ids, league_name),
            league_name=league_name,
        )

    def _start_scraping_thread(self, target, args, league_name: str) -> bool:
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

            self._scraping_thread = threading.Thread(
                target=target,
                args=args,
                daemon=True,
            )
            self._scraping_thread.start()

            from core.extensions import socketio
            socketio.emit('scraping_started', {'name': league_name})
            logger.info(f"Scrapowanie uruchomione w tle ({target.__name__})")
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

    def get_statistics(self) -> Dict:
        """Statystyki gier w bazie (do wyświetlenia na liście gier)."""
        from app.models.game import Game
        try:
            return {
                'total':       Game.query.count(),
                'finished':    Game.query.filter_by(status=Game.STATUS_FINISHED).count(),
                'in_progress': Game.query.filter_by(status=Game.STATUS_PENDING).count(),
                'not_started': Game.query.filter_by(status=Game.STATUS_NOT_STARTED).count(),
            }
        except Exception:
            return {'total': 0, 'finished': 0, 'in_progress': 0, 'not_started': 0}

    # ── Wątek roboczy ─────────────────────────────────────────────────────────

    def _scrape_worker(self, app, league_urls: List[str], league_name: str, league_id: Optional[int] = None):
        """Wątek w tle — pobiera HTML (MZPN), przetwarza, zapisuje do bazy."""
        with app.app_context():
            from core.extensions import socketio
            try:
                from app.managers.scrapers.malopolskizpn.game_scraper import GameScraper
                from app.models.scraper import Scraper
                scraper       = GameScraper()
                scraped_games = scraper.scrape_multiple_leagues(league_urls, league_id=league_id)
                mzpn_scraper  = Scraper.get_by_folder('malopolskizpn')
                stats         = self._process_scraped_games(
                    scraped_games,
                    scraper_id=mzpn_scraper.id if mzpn_scraper else None,
                )

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

    def _scrape_superscore_worker(self, app, season_ids: List[str], league_name: str):
        """Wątek w tle — pobiera dane z superscore API, przetwarza, zapisuje do bazy."""
        with app.app_context():
            from core.extensions import socketio
            try:
                from app.managers.scrapers.superscore.superscore_game_scraper import SuperscoreGameScraper
                from app.models.scraper import Scraper
                scraper       = SuperscoreGameScraper()
                scraped_games = scraper.scrape_multiple_seasons(season_ids)
                superscore_scraper = Scraper.get_by_folder('superscore')
                stats         = self._process_scraped_games(
                    scraped_games,
                    scraper_id=superscore_scraper.id if superscore_scraper else None,
                )

                self._status = {
                    'status':        'completed',
                    'total_scraped': stats['total_scraped'],
                    'updated':       stats['updated'],
                    'new_pending':   stats['new_pending'],
                    'error':         None,
                }
                logger.info(
                    f"Scrapowanie superscore zakończone: {stats['total_scraped']} łącznie, "
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
                logger.error(f"Błąd scrapowania superscore w wątku: {e}", exc_info=True)
                self._status = {
                    'status': 'error', 'total_scraped': 0,
                    'updated': 0, 'new_pending': 0, 'error': str(e),
                }
                socketio.emit('scraping_error', {
                    'status': 'error', 'name': league_name, 'error': str(e),
                })

    # ── Przetwarzanie i zapis do bazy ─────────────────────────────────────────

    def _process_scraped_games(self, scraped_games: List[Dict], scraper_id: Optional[int] = None) -> Dict[str, int]:
        """
        Przetworz listę meczów z scrapera i zapisz do bazy.

        Identyfikacja istniejącego meczu:
          - jeśli scraper_id podany i mecz ma foreign_id (superscore: event['id'])
            → najpierw po GameForeignId (stabilne, przetrwa np. zmianę kolejki),
          - w przeciwnym razie po league_id + round + home_team_id + away_team_id
            (MZPN nie daje foreign_id per mecz — inaczej niż futsal/superscore).

        Identyfikacja drużyn:
          - jeśli scraper_id podany i mecz ma home/away_team_foreign_id (superscore:
            'slug/hash') → najpierw po TeamForeignId (już potwierdzone przez admina
            w scraperze drużyn — pewniejsze niż dopasowanie po nazwie),
          - fallback: dopasowanie po znormalizowanej nazwie (jak dotychczas; jedyna
            ścieżka dla MZPN, które nie ma żadnego ID per drużyna).

        Logika aktualizacji:
          - Jeśli WWW mówi STATUS_NOT_STARTED ale DB ma bardziej zaawansowany status
            (np. mecz właśnie trwa lub skończył się) → pomijamy, DB jest aktualniejsza.
          - W przeciwnym razie aktualizujemy zmienione pola.

        Dla nowych meczów tworzy też 2 okresy (1. i 2. połowa).
        """
        from app.models.game import Game
        from app.models.period import Period
        from app.models.league import League
        from app.models.team import Team
        from app.models.team_foreign_id import TeamForeignId
        from app.models.game_foreign_id import GameForeignId
        from app.models.game_scraper_snapshot import GameScraperSnapshot
        from app.models.game_conflict import GameConflict

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
        STATUS_IN_PROGRESS = Game.STATUS_PENDING
        STATUS_FINISHED    = Game.STATUS_FINISHED

        for gd in scraped_games:
            home_team = away_team = None
            if scraper_id and gd.get('home_team_foreign_id') and gd.get('away_team_foreign_id'):
                home_id = TeamForeignId.get_local_id(scraper_id, gd['home_team_foreign_id'])
                away_id = TeamForeignId.get_local_id(scraper_id, gd['away_team_foreign_id'])
                if home_id:
                    home_team = Team.query.get(home_id)
                if away_id:
                    away_team = Team.query.get(away_id)

            if not home_team:
                home_team = team_lookup.get(_normalize(gd['home_team_name']))
            if not away_team:
                away_team = team_lookup.get(_normalize(gd['away_team_name']))

            if not home_team or not away_team:
                logger.warning(
                    f"Pomijam kolejka={gd['round']} "
                    f"'{gd['home_team_name']}' vs '{gd['away_team_name']}' — brak drużyny w bazie"
                )
                continue

            scraper_status  = gd['status']
            # Mapuj status scrapera (może używać 1=IN_PROGRESS) na stałe modelu
            if scraper_status == 1:
                status = STATUS_IN_PROGRESS
            elif scraper_status == 2:
                status = STATUS_FINISHED
            else:
                status = STATUS_NOT_STARTED

            home_goals      = gd['home_team_goals']
            away_goals      = gd['away_team_goals']
            parsed_date     = self._parse_date(gd['date'])

            # ── Szukaj istniejącego meczu ─────────────────────────────────
            existing = None
            game_foreign_id = gd.get('foreign_id')
            if scraper_id and game_foreign_id:
                existing_id = GameForeignId.get_local_id(scraper_id, game_foreign_id)
                if existing_id:
                    existing = Game.query.get(existing_id)

            if existing is None:
                # Najpierw próbuj po kolejce + drużynach (dokładne dopasowanie).
                # Jeśli nie znaleziono (np. scraper zwrócił round=0), szukaj tylko
                # po drużynach — w sezonie każda para (home, away) jest unikalna.
                existing = Game.query.filter_by(
                    league_id    = league_id,
                    round        = gd['round'],
                    home_team_id = home_team.id,
                    away_team_id = away_team.id,
                ).first()

            if existing is None:
                existing = Game.query.filter_by(
                    league_id    = league_id,
                    home_team_id = home_team.id,
                    away_team_id = away_team.id,
                ).first()
                if existing:
                    logger.debug(
                        f"Dopasowano po drużynach (round={gd['round']} → db.round={existing.round}): "
                        f"{gd['home_team_name']} vs {gd['away_team_name']}"
                    )

            if existing:
                if scraper_id and game_foreign_id and not existing.get_foreign_id(scraper_id):
                    existing.set_foreign_id(scraper_id, game_foreign_id)

                # Nie cofaj statusu do NOT_STARTED, jeśli DB ma już PENDING albo
                # FINISHED — żaden scraper nie ustawia PENDING/FINISHED i nie
                # zwraca teraz NOT_STARTED dla tego samego meczu, więc taki DB
                # stan może pochodzić tylko od użytkownika (np. ręcznie
                # wystartowany/zakończony mecz transmitowany na żywo) —
                # użytkownik ma priorytet, żaden scraper go nie cofa.
                if existing.status in (STATUS_FINISHED, STATUS_IN_PROGRESS) and status == STATUS_NOT_STARTED:
                    logger.debug(
                        f"Pomijam kolejka={gd['round']} "
                        f"{gd['home_team_name']} vs {gd['away_team_name']} "
                        f"— www=NOT_STARTED, db={'FINISHED' if existing.status == STATUS_FINISHED else 'PENDING'}"
                    )
                    continue

                # ── Zgodność między scraperami (jeśli mecz ma już dane z INNEGO
                # scrapera) — patrz _reconcile_cross_scraper_data. `resolved`
                # to finalny zestaw pól do zapisania (może łączyć dane obu
                # scraperów — patrz "uzupełnianie None" w tej metodzie).
                resolved = {
                    'home_team_goals': home_goals,
                    'away_team_goals': away_goals,
                    'home_ht_goals':   gd['home_ht_goals'],
                    'away_ht_goals':   gd['away_ht_goals'],
                    'date':            parsed_date,
                    'status':          status,
                }
                merged = False
                if scraper_id:
                    proceed, resolved, merged = self._reconcile_cross_scraper_data(
                        existing, league_id, scraper_id, gd, status, parsed_date,
                        GameScraperSnapshot, GameConflict,
                    )
                    if not proceed:
                        continue

                changes = {
                    'home_team_goals': (existing.home_team_goals, resolved['home_team_goals']),
                    'away_team_goals': (existing.away_team_goals, resolved['away_team_goals']),
                    'status':          (existing.status,          status),
                    'date':            (existing.date,            resolved['date']),
                }
                changed = [f for f, (old, new) in changes.items() if old != new]
                if changed:
                    for field in changed:
                        setattr(existing, field, changes[field][1])
                    existing.updated_at = datetime.utcnow()
                    logger.info(f"Zaktualizowano mecz id={existing.id}: {changed}")
                    updated_count += 1
                # Okresy odświeżamy zawsze (nie tylko gdy changed) — resolved
                # może nieść nowy podział na połowy (np. z MZPN) nawet gdy wynik
                # końcowy/data na Game się nie zmieniły; _upsert_periods jest
                # idempotentny więc powtórka z tymi samymi danymi jest nieszkodliwa.
                self._upsert_periods(existing, resolved, Period)
                if not changed and merged:
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
                if scraper_id and game_foreign_id:
                    game.set_foreign_id(scraper_id, game_foreign_id)
                if scraper_id:
                    # Brak innego scrapera do porównania na tym etapie (mecz dopiero
                    # co powstał) — zapisz tylko własny snapshot na przyszłość.
                    GameScraperSnapshot.upsert(
                        scraper_id, game.id, home_goals, away_goals,
                        gd['home_ht_goals'], gd['away_ht_goals'], parsed_date, status,
                    )
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

    # ── Zgodność danych między scraperami ───────────────────────────────────────

    @staticmethod
    def _malopolskizpn_scraper_id() -> Optional[int]:
        from app.models.scraper import Scraper
        scraper = Scraper.get_by_folder('malopolskizpn')
        return scraper.id if scraper else None

    @staticmethod
    def _fill_none(own_value, other_value):
        """Gdy jedna strona nie ma danych (None) a druga ma — bierzemy tę
        niepustą, bez pytania admina. Zwraca None jeśli obie strony puste."""
        if own_value is None:
            return other_value
        return own_value

    def _reconcile_cross_scraper_data(self, existing_game, league_id: int, scraper_id: int,
                                       gd: Dict, status: int, parsed_date,
                                       GameScraperSnapshot, GameConflict):
        """
        Porównuje świeżo zescrapowane dane (gd, od scraper_id) z tym, co ostatnio
        zaobserwował INNY scraper dla tego samego meczu (GameScraperSnapshot).

        Dla wyniku końcowego (home/away_team_goals) i daty — pól, których
        niezgodność ma znaczenie:
          - obie strony mają wartość i się różnią → prawdziwy konflikt,
          - jedna strona ma None a druga wartość → NIE jest to konflikt,
            bierzemy wartość niepustą (żadna decyzja admina niepotrzebna),
          - obie None albo równe → bez zmian.

        Wynik do przerwy (home/away_ht_goals) nigdy nie jest polem
        konfliktowym — gdy wynik końcowy jest spójny (patrz wyżej), okresy
        budujemy z danych malopolskizpn, jeśli je ma (bogatsze/bardziej
        wiarygodne wg ustalenia z użytkownikiem); w przeciwnym razie
        uzupełniamy braki (None) wartością z drugiej strony tak samo jak wynik.

        Prawdziwy konflikt (wynik i/lub data) → NIE aplikuj automatycznie.
        Jeśli dokładnie taka sama niezgodność była już wcześniej ręcznie
        rozstrzygnięta (błąd na źródłowej stronie nadal niepoprawiony) →
        pomiń po cichu, nie zgłaszaj ponownie. W przeciwnym razie utwórz/
        odśwież otwarty GameConflict do przeglądu przez admina.

        Zawsze (niezależnie od wyniku porównania) zapisuje świeży
        GameScraperSnapshot dla scraper_id, żeby kolejne porównania (z dowolnej
        strony) miały aktualny punkt odniesienia.

        Returns:
            (proceed: bool, resolved: dict, merged: bool) — resolved to finalny
            zestaw pól (home/away_team_goals, home/away_ht_goals, date, status)
            do zapisania w Game i _upsert_periods gdy proceed=True. merged=True
            gdy istniały dane z innego scrapera do porównania (do statystyk).
        """
        own = {
            'home_team_goals': gd['home_team_goals'],
            'away_team_goals': gd['away_team_goals'],
            'home_ht_goals':   gd['home_ht_goals'],
            'away_ht_goals':   gd['away_ht_goals'],
            'date':            parsed_date,
            'status':          status,
        }

        other = GameScraperSnapshot.get_other(existing_game.id, scraper_id)

        GameScraperSnapshot.upsert(
            scraper_id, existing_game.id,
            gd['home_team_goals'], gd['away_team_goals'],
            gd['home_ht_goals'], gd['away_ht_goals'],
            parsed_date, status,
        )

        if other is None:
            return True, own, False

        conflicting_fields = []
        for field, other_value in (
            ('home_team_goals', other.home_team_goals),
            ('away_team_goals', other.away_team_goals),
            ('date',            other.date),
        ):
            own_value = own[field]
            if own_value is not None and other_value is not None and own_value != other_value:
                conflicting_fields.append(field)

        if conflicting_fields:
            already_resolved = GameConflict.find_matching_resolution(
                existing_game.id,
                scraper_id, gd['home_team_goals'], gd['away_team_goals'], parsed_date,
                other.scraper_id, other.home_team_goals, other.away_team_goals, other.date,
            )
            if already_resolved:
                logger.debug(f"Konflikt danych meczu id={existing_game.id} już rozstrzygnięty wcześniej — pomijam")
                return False, own, True

            GameConflict.upsert_open(
                existing_game.id, league_id,
                scraper_id, gd['home_team_goals'], gd['away_team_goals'],
                gd['home_ht_goals'], gd['away_ht_goals'], parsed_date,
                other.scraper_id, other.home_team_goals, other.away_team_goals,
                other.home_ht_goals, other.away_ht_goals, other.date,
            )
            logger.warning(
                f"Niespójność danych meczu id={existing_game.id} między scraperami "
                f"({', '.join(conflicting_fields)}) — czeka na decyzję admina"
            )
            return False, own, True

        # Brak prawdziwego konfliktu — uzupełnij ewentualne braki (None) wartością
        # z drugiej strony.
        resolved = {
            'home_team_goals': self._fill_none(own['home_team_goals'], other.home_team_goals),
            'away_team_goals': self._fill_none(own['away_team_goals'], other.away_team_goals),
            'date':            self._fill_none(own['date'], other.date),
            'status':          own['status'],
            'home_ht_goals':   own['home_ht_goals'],
            'away_ht_goals':   own['away_ht_goals'],
        }

        mzpn_scraper_id = self._malopolskizpn_scraper_id()
        if other.scraper_id == mzpn_scraper_id and other.home_ht_goals is not None:
            # Wynik spójny — preferuj bogatszy/bardziej wiarygodny podział na
            # połowy z malopolskizpn, niezależnie od tego, kto aktualnie zapisuje.
            resolved['home_ht_goals'] = other.home_ht_goals
            resolved['away_ht_goals'] = other.away_ht_goals
        else:
            resolved['home_ht_goals'] = self._fill_none(own['home_ht_goals'], other.home_ht_goals)
            resolved['away_ht_goals'] = self._fill_none(own['away_ht_goals'], other.away_ht_goals)

        return True, resolved, True

    def get_pending_game_conflicts(self, league_id: int) -> List:
        from app.models.game_conflict import GameConflict
        return GameConflict.get_open_for_league(league_id)

    def resolve_game_conflict(self, conflict_id: int, chosen_scraper_id: int):
        """
        Zatwierdź konflikt: zastosuj dane wskazanego scrapera (wynik, wynik do
        przerwy, data) jako prawidłowe. Wiersz NIE jest usuwany — zostaje
        oznaczony jako rozwiązany, żeby ten sam (niepoprawiony) błąd źródła nie
        był zgłaszany ponownie przy kolejnych scrapowaniach.
        """
        from app.models.game import Game
        from app.models.period import Period
        from app.models.game_conflict import GameConflict

        conflict = GameConflict.query.get(conflict_id)
        if not conflict:
            raise ValueError("Nie znaleziono konfliktu do rozwiązania")
        if chosen_scraper_id not in (conflict.scraper_a_id, conflict.scraper_b_id):
            raise ValueError("Wskazany scraper nie jest jedną ze stron tego konfliktu")

        game = Game.query.get(conflict.game_id)
        if not game:
            raise ValueError("Nie znaleziono meczu powiązanego z konfliktem")

        if chosen_scraper_id == conflict.scraper_a_id:
            home, away = conflict.scraper_a_home_goals, conflict.scraper_a_away_goals
            home_ht, away_ht = conflict.scraper_a_home_ht_goals, conflict.scraper_a_away_ht_goals
            date = conflict.scraper_a_date
        else:
            home, away = conflict.scraper_b_home_goals, conflict.scraper_b_away_goals
            home_ht, away_ht = conflict.scraper_b_home_ht_goals, conflict.scraper_b_away_ht_goals
            date = conflict.scraper_b_date

        game.home_team_goals = home
        game.away_team_goals = away
        game.date = date
        if home is not None and away is not None:
            game.status = Game.STATUS_FINISHED
        game.updated_at = datetime.utcnow()

        self._upsert_periods(game, {
            'home_team_goals': home, 'away_team_goals': away,
            'home_ht_goals': home_ht, 'away_ht_goals': away_ht,
            'status': 2 if (home is not None and away is not None) else 0,
        }, Period)

        conflict.resolved_at = datetime.utcnow()
        conflict.resolved_scraper_id = chosen_scraper_id
        db.session.commit()
        return game

    # ── Okresy ───────────────────────────────────────────────────────────────

    @staticmethod
    def _upsert_periods(game, gd: Dict, Period):
        """
        Utwórz lub zaktualizuj dwa okresy (1. i 2. połowa) dla meczu.

        Bramki 2. połowy = bramki końcowe − bramki do przerwy.
        """
        STATUS_FINISHED    = Period.STATUS_FINISHED
        STATUS_NOT_STARTED = Period.STATUS_NOT_STARTED
        STATUS_IN_PROGRESS = Period.STATUS_PENDING

        scraper_status = gd['status']
        is_finished    = (scraper_status == 2)
        is_in_progress = (scraper_status == 1)

        home_ht  = gd['home_ht_goals'] or 0
        away_ht  = gd['away_ht_goals'] or 0
        home_ft  = gd['home_team_goals'] or 0
        away_ft  = gd['away_team_goals'] or 0
        home_2h  = (home_ft - home_ht) if is_finished else 0
        away_2h  = (away_ft - away_ht) if is_finished else 0

        # Przy meczu w trakcie: jeśli dostępny wynik przerwy → 1. poł. skończona,
        # brak → 1. poł. w trakcie
        has_ht_score  = (gd['home_ht_goals'] is not None)
        p1_status     = (STATUS_FINISHED    if (is_finished or (is_in_progress and has_ht_score))
                         else STATUS_IN_PROGRESS if is_in_progress
                         else STATUS_NOT_STARTED)
        p2_status     = (STATUS_FINISHED    if is_finished
                         else STATUS_IN_PROGRESS if (is_in_progress and has_ht_score)
                         else STATUS_NOT_STARTED)

        periods_data = [
            {
                'period_order':  1,
                'description':   '1. połowa',
                'main_timer_name': f'{game.home_team.short_name}x{game.away_team.short_name} p:1',
                'limit':         2700000,    # 45 min w ms
                'initial_time':  0,
                'home_goals':    home_ht if (is_finished or is_in_progress) else 0,
                'away_goals':    away_ht if (is_finished or is_in_progress) else 0,
                'status':        p1_status,
            },
            {
                'period_order':  2,
                'description':   '2. połowa',
                'main_timer_name': f'{game.home_team.short_name}x{game.away_team.short_name} p:2',
                'limit':         2700000,
                'initial_time':  2700000,    # offset 45:00 dla overlay
                'home_goals':    home_2h,
                'away_goals':    away_2h,
                'status':        p2_status,
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
        from app.models.team_foreign_id import TeamForeignId
        from app.models.league_team import LeagueTeam
        from app.models.scraper import Scraper

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

        superscore_scraper = Scraper.get_by_folder('superscore')
        if superscore_scraper:
            team_ids = {t.id for t in teams}
            superscore_names = (
                TeamForeignId.query
                .filter(
                    TeamForeignId.scraper_id == superscore_scraper.id,
                    TeamForeignId.team_id.in_(team_ids),
                )
                .all()
            )
            teams_by_id = {t.id: t for t in teams}
            for row in superscore_names:
                lookup[_normalize(row.foreign_id)] = teams_by_id[row.team_id]

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