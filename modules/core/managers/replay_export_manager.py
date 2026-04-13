"""
ReplayExportManager — eksportuje dane powtórek z bazy do plików CSV.

Logika odpowiada export_replays.py z katalogu instance/, ale:
- używa SQLAlchemy zamiast surowego sqlite3 (działa w kontekście Flask)
- jest wywoływalna programistycznie (z sekwencji, API, SocketIO)
- zwraca ustrukturyzowany wynik zamiast drukować na stdout

Struktura wyjścia:
    <DATA_DIR>/<YYYY-MM-DD>_<home_short>x<away_short>/
        <video_filename>.csv         ← game_events (główna kamera / OBS)
        <video_filename>.csv         ← event_cameras (kamery zewnętrzne)

Format każdego CSV:
    replay_start_time, replay_end_time, event_short_name
    (czasy w sekundach, zaokrąglone w górę — gotowe do użycia przez ffmpeg/player)
"""

import csv
import math
import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

from flask import current_app

def _get_game():
    from core.models.base_game import get_game_model
    return get_game_model()


logger = logging.getLogger(__name__)


class ReplayExportManager:

    def __init__(self, data_dir: Path):
        """
        Args:
            data_dir: katalog główny eksportu,
                      np. Path('app/data') — podkatalogi tworzone automatycznie.
        """
        self.data_dir = Path(data_dir)

    # =========================================================================
    # PUBLICZNE API
    # =========================================================================

    def export_current_game(self) -> dict:
        """
        Eksportuje powtórki aktualnie wybranego meczu (settings.current_game_id).

        Przeznaczone do wywołania z sekwencji (po stop_recording) lub z UI
        jako operacja "wyeksportuj bieżący mecz".

        Returns:
            dict z polami: game_id, folder, files_saved, errors
        """
        from core.models.settings import get_settings_model
        Settings = get_settings_model()
        settings = Settings.get_settings()
        game_id  = settings.current_game_id

        if not game_id:
            msg = "Brak aktualnie wybranego meczu (settings.current_game_id is None)"
            logger.warning(f"[ReplayExport] {msg}")
            return {'game_id': None, 'folder': None, 'files_saved': 0,
                    'errors': [msg]}

        return self.export_game(game_id)

    def export_game(self, game_id: int) -> dict:
        """
        Eksportuje powtórki dla podanego game_id.

        Używa SQLAlchemy — musi być wywołane w kontekście Flask (app_context).

        Returns:
            dict z polami: game_id, folder, files_saved, errors
        """
        from core.models.base_game import BaseGame

        game = _get_game().query.get(game_id)
        if not game:
            msg = f"Mecz id={game_id} nie istnieje"
            logger.error(f"[ReplayExport] {msg}")
            return {'game_id': game_id, 'folder': None, 'files_saved': 0,
                    'errors': [msg]}

        folder  = self._make_folder(game)
        errors  = []
        saved   = 0

        logger.info(f"[ReplayExport] Eksport meczu {game_id} → {folder}")

        # --- game_events (główna kamera / OBS fallback) ---
        ge_rows = self._get_game_event_rows(game_id)
        if ge_rows:
            groups = self._group_by_video(ge_rows)
            logger.info(f"[ReplayExport]   game_events: {len(ge_rows)} wierszy, "
                        f"{len(groups)} plik(ów)")
            for vpath, rows in groups.items():
                fname = self._csv_filename(vpath)
                try:
                    self._save_csv(folder, fname, rows)
                    saved += 1
                    logger.info(f"[ReplayExport]   [OK] {fname} ({len(rows)} wierszy)")
                except Exception as e:
                    msg = f"Błąd zapisu {fname}: {e}"
                    logger.error(f"[ReplayExport]   [ERR] {msg}")
                    errors.append(msg)
        else:
            logger.info("[ReplayExport]   game_events: brak wierszy z video_path i czasami")

        # --- event_cameras (kamery zewnętrzne) ---
        ec_rows = self._get_event_camera_rows(game_id)
        if ec_rows:
            groups = self._group_by_video(ec_rows)
            logger.info(f"[ReplayExport]   event_cameras: {len(ec_rows)} wierszy, "
                        f"{len(groups)} plik(ów)")
            for vpath, rows in groups.items():
                fname = self._csv_filename(vpath)
                try:
                    self._save_csv(folder, fname, rows)
                    saved += 1
                    logger.info(f"[ReplayExport]   [OK] {fname} ({len(rows)} wierszy)")
                except Exception as e:
                    msg = f"Błąd zapisu {fname}: {e}"
                    logger.error(f"[ReplayExport]   [ERR] {msg}")
                    errors.append(msg)
        else:
            logger.info("[ReplayExport]   event_cameras: brak rekordów")

        result = {
            'game_id':    game_id,
            'folder':     str(folder),
            'files_saved': saved,
            'errors':     errors,
        }

        if saved:
            logger.info(f"[ReplayExport] ✅ Gotowe. Zapisano {saved} plik(ów) CSV.")
        else:
            logger.warning("[ReplayExport] ⚠️  Nie zapisano żadnych plików — brak danych powtórek.")

        return result

    def list_exportable_games(self) -> list:
        """
        Zwraca listę meczów które mają zarejestrowane zdarzenia z danymi wideo.
        Przeznaczone dla UI (np. select w formularzu eksportu).

        Returns:
            lista słowników: game_id, home_short, away_short, date, event_count
        """
        from core.models.base_game import BaseGame
        from core.models.game_event import GameEvent

        games = (
            _get_game()
            .join(Game.game_events)
            .filter(GameEvent.video_path.isnot(None))
            .distinct()
            .order_by(Game.date.desc())
            .all()
        )

        result = []
        for game in games:
            count = (
                GameEvent.query
                .filter_by(game_id=game.id)
                .filter(GameEvent.video_path.isnot(None))
                .count()
            )
            result.append({
                'game_id':    game.id,
                'home_short': game.home_team.short_name if game.home_team else '?',
                'away_short': game.away_team.short_name if game.away_team else '?',
                'date':       game.date.isoformat() if game.date else None,
                'event_count': count,
            })
        return result

    # =========================================================================
    # PRYWATNE — pobieranie danych
    # =========================================================================

    def _get_game_event_rows(self, game_id: int) -> list:
        """game_events z wypełnionym video_path i czasami powtórki."""
        from core.models.game_event import GameEvent
        from core.models.event import Event

        rows = (
            GameEvent.query
            .join(GameEvent.event)
            .filter(
                GameEvent.game_id == game_id,
                GameEvent.video_path.isnot(None),
                GameEvent.replay_start_time.isnot(None),
                GameEvent.replay_end_time.isnot(None),
            )
            .order_by(GameEvent.replay_start_time.asc())
            .all()
        )
        return [
            {
                'video_path':        r.video_path,
                'replay_start_time': r.replay_start_time,
                'replay_end_time':   r.replay_end_time,
                'event_short_name':  r.event.short_name if r.event else '',
            }
            for r in rows
        ]

    def _get_event_camera_rows(self, game_id: int) -> list:
        """event_cameras dla danego meczu z wypełnionym video_path."""
        from core.models.event_camera import EventCamera
        from core.models.game_event import GameEvent
        from core.models.event import Event

        rows = (
            EventCamera.query
            .join(EventCamera.game_event)
            .join(GameEvent.event)
            .filter(
                GameEvent.game_id == game_id,
                EventCamera.video_path.isnot(None),
            )
            .order_by(EventCamera.replay_start_time.asc())
            .all()
        )
        return [
            {
                'video_path':        r.video_path,
                'replay_start_time': r.replay_start_time,
                'replay_end_time':   r.replay_end_time,
                'event_short_name':  r.game_event.event.short_name
                                     if r.game_event and r.game_event.event else '',
            }
            for r in rows
        ]

    # =========================================================================
    # PRYWATNE — zapis plików
    # =========================================================================

    def _make_folder(self, game) -> Path:
        """
        Tworzy i zwraca katalog dla meczu:
            <data_dir>/<YYYY-MM-DD>_<home_short>x<away_short>/
        """
        date_part  = game.date.strftime('%Y-%m-%d') if game.date else 'no-date'
        home_short = game.home_team.short_name if game.home_team else 'HOM'
        away_short = game.away_team.short_name if game.away_team else 'AWY'
        folder_name = self._safe_name(f"{date_part}_{home_short}x{away_short}")
        folder = self.data_dir / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _safe_name(text: str) -> str:
        """Zamienia niedozwolone znaki nazwy katalogu na '_'."""
        keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
        return "".join(c if c in keep else "_" for c in text)

    @staticmethod
    def _csv_filename(video_path: str) -> str:
        """<nazwa_pliku_wideo>.csv"""
        return Path(video_path).name + ".csv"

    @staticmethod
    def _group_by_video(rows: list) -> dict:
        """
        Grupuje wiersze według video_path.
        Czasy przelicza ms → sekundy (ceil), sortuje chronologicznie.
        """
        groups = defaultdict(list)
        for row in rows:
            groups[row['video_path']].append({
                'replay_start_time': math.ceil(row['replay_start_time'] / 1000.0),
                'replay_end_time':   math.ceil(row['replay_end_time']   / 1000.0),
                'event_short_name':  row['event_short_name'],
            })
        for k in groups:
            groups[k].sort(key=lambda r: r['replay_start_time'])
        return groups

    @staticmethod
    def _save_csv(folder: Path, filename: str, rows: list) -> Path:
        """Zapisuje plik CSV z nagłówkiem."""
        path = folder / filename
        fields = ['replay_start_time', 'replay_end_time', 'event_short_name']
        with open(str(path), 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path