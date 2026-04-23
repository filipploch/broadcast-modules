"""
app.managers — managery modułu futsal-nalf.

Rozszerza core.managers o managery specyficzne dla futsalu.
Eksportuje ujednolicony interfejs: jedno miejsce do pobierania
wszystkich managerów niezależnie od tego czy są w core czy w module.
"""
from core.managers import (
    initialize_core_managers,
    shutdown_core_managers,
    get_hub_client,
    get_timer_manager,
    get_recorder_manager,
    get_obs_ws_manager,
    get_sequence_manager,
    get_plugin_manager,
    get_current_game_manager,
    get_replay_export_manager,
)
from flask import current_app
import threading

# ── Singletony specyficzne dla futsalu ───────────────────────────────────────
_game_manager          = None


def initialize_all_managers(app):
    import core.managers as _core_mgrs
    from app.managers.timer_manager import TimerManager
    _core_mgrs._timer_manager_class = TimerManager
    """
    Inicjalizuje wszystkie managery: najpierw core, potem futsal-specifyczne.
    Wywoływana z app/__init__.py w wątku tła.
    """
    initialize_core_managers(app)
    # Futsal-specific managers są lazy-init — nie trzeba ich tu startować


def shutdown_all_managers():
    """Zatrzymuje wszystkie managery (core + futsal-specific)."""
    global _game_manager
    shutdown_core_managers()
    _game_manager          = None


# ── Lazy getters futsal-specific ─────────────────────────────────────────────



# ── Direct imports — managery bez zależności od huba ─────────────────────────
from core.managers.game_manager import GameManager
from core.managers.league_manager import LeagueManager
from core.managers.team_manager import TeamManager
from core.managers.season_manager import SeasonManager
from core.managers.player_manager import PlayerManager
from core.managers.shootout_manager import ShootoutManager
from core.managers.game_event_manager import GameEventManager
from app.managers.team_scraper_manager import TeamScraperManager
from app.managers.player_scraper_manager import PlayerScraperManager
from app.managers.game_scraper_manager import GameScraperManager

# Managery z core re-eksportowane dla wygody importów w module
from core.managers.camera_manager import CameraManager
from core.managers.commentator_manager import CommentatorManager
from core.managers.referee_manager import RefereeManager
from core.managers.stadium_manager import StadiumManager
from app.managers.period_manager import PeriodManager
from core.managers.event_manager import EventManager
from core.managers.game_camera_manager import GameCameraManager
from core.managers.game_commentator_manager import GameCommentatorManager
from core.managers.game_referee_manager import GameRefereeManager
from core.managers.game_player_manager import GamePlayerManager
