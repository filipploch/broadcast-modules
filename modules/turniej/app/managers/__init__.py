"""
app.managers — managery modułu turniej.
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


def initialize_all_managers(app):
    import core.managers as _core_mgrs
    from app.managers.timer_manager import TimerManager
    _core_mgrs._timer_manager_class = TimerManager
    initialize_core_managers(app)


def shutdown_all_managers():
    shutdown_core_managers()


# Managery z core re-eksportowane dla wygody
from core.managers.camera_manager import CameraManager
from core.managers.commentator_manager import CommentatorManager
from core.managers.event_manager import EventManager
from core.managers.game_camera_manager import GameCameraManager
from core.managers.game_commentator_manager import GameCommentatorManager
from core.managers.game_event_manager import GameEventManager
from core.managers.game_manager import GameManager
from core.managers.game_referee_manager import GameRefereeManager
from core.managers.league_manager import LeagueManager
from core.managers.player_manager import PlayerManager
from core.managers.referee_manager import RefereeManager
from core.managers.season_manager import SeasonManager
from core.managers.stadium_manager import StadiumManager

from app.managers.game_player_manager import GamePlayerManager
from app.managers.period_manager import PeriodManager
from app.managers.timer_manager import TimerManager
