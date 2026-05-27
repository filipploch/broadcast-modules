"""
app.managers — managery modułu garbarnia.

Rozszerza core.managers o managery specyficzne dla piłki nożnej.
Eksportuje ujednolicony interfejs: jedno miejsce do pobierania
wszystkich managerów niezależnie od tego czy są w core czy w module.
"""
from core.managers import (
    initialize_core_managers,
    shutdown_core_managers,
    get_hub_client,
    get_timer_manager,
    get_period_manager,
    get_recorder_manager,
    get_obs_ws_manager,
    get_sequence_manager,
    get_plugin_manager,
    get_current_game_manager,
    get_replay_export_manager,
)

_game_manager = None


def initialize_all_managers(app):
    import core.managers as _core_mgrs
    from app.managers.timer_manager import TimerManager
    from app.managers.period_manager import PeriodManager
    _core_mgrs._timer_manager_class = TimerManager
    _core_mgrs._period_manager_class = PeriodManager
    """
    Inicjalizuje wszystkie managery: najpierw core, potem futsal-specifyczne.
    Wywoływana z app/__init__.py w wątku tła.
    """
    initialize_core_managers(app)


def shutdown_all_managers():
    global _game_manager
    shutdown_core_managers()
    _game_manager = None


# ── Direct imports ────────────────────────────────────────────────────────────
# Managery z core re-eksportowane dla wygody importów w module
from core.managers.camera_manager import CameraManager
from core.managers.commentator_manager import CommentatorManager
from core.managers.event_manager import EventManager
from core.managers.game_camera_manager import GameCameraManager
from core.managers.game_commentator_manager import GameCommentatorManager
from core.managers.game_event_manager import GameEventManager
from core.managers.game_manager import GameManager
from core.managers.game_referee_manager import GameRefereeManager
# hub_client
from core.managers.league_manager import LeagueManager
# obs_ws_manager
from core.managers.player_manager import PlayerManager
# plugin_manager
# recorder_manager
from core.managers.referee_manager import RefereeManager
# replay_export_manager
from core.managers.season_manager import SeasonManager
# sequence_manager
# shootout_kick_manager
from core.managers.shootout_kick_manager import ShootoutKickManager
from core.managers.shootout_manager import ShootoutManager
from core.managers.stadium_manager import StadiumManager

from app.managers.game_player_manager import GamePlayerManager
from app.managers.game_scraper_manager import GameScraperManager
from app.managers.period_manager import PeriodManager
from app.managers.player_scraper_manager import PlayerScraperManager
from app.managers.team_scraper_manager import TeamScraperManager
from app.managers.team_manager import TeamManager
from app.managers.timer_manager import TimerManager
from app.managers.substitution_manager import SubstitutionManager
from app.managers.substitution_manager import SubstitutionItem
