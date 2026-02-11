"""Managers package - HUB manages plugin processes

SIMPLIFIED VERSION - No mDNS dependencies required
Just uses HUB_HOST from config directly

Managers:
- PluginManager: Loads plugin metadata from database
- HubClient: Connects to HUB, declares required plugins
- TimerManager: Business logic for timers (lazy init)
- CurrentGameManager: Business logic for games (lazy init)
- RecorderManager: Business logic for recording (lazy init)
"""
from flask import current_app
import threading
import time

# Global instances
# _plugin_manager = None
_hub_client = None
_current_game_manager = None
_recorder_manager = None
_timer_manager = None
_team_scraper_manager = None
_initialization_lock = threading.Lock()
_initialized = False


def initialize_all_managers(app):
    """
    Initialize all managers

    Flow:
    1. PluginManager loads plugin list from DB
    2. HubClient connects to HUB (uses HUB_HOST from config)
    3. HubClient registers Flask as main_module
    4. HubClient declares required plugins → HUB STARTS THEM!
    5. Other managers (Timer/Game/Recorder) lazy init when needed
    """
    # global _plugin_manager, _hub_client, _current_game_manager, _recorder_manager
    global _hub_client, _current_game_manager, _recorder_manager, _timer_manager, _team_scraper_manager, _initialized

    with _initialization_lock:
        if _initialized:
            app.logger.warning("Managers already initialized")
            return

        app.logger.info("=" * 60)
        app.logger.info("INITIALIZING MANAGERS")
        app.logger.info("=" * 60)

        try:
            # ========================================================================
            # 1. PLUGIN MANAGER (Metadata Only)
            # ========================================================================
            # from app.managers.plugin_manager import PluginManager
            # _plugin_manager = PluginManager()
            # _plugin_manager.load_plugins()
            # app.logger.info("✅ Plugin Manager initialized")

            # ========================================================================
            # 2. HUB CLIENT
            # ========================================================================
            from app.managers.hub_client import HubClient

            # Get HUB URL from config
            hub_url = app.config['HUB_HOST']

            app.logger.info(f"Connecting to HUB: {hub_url}")

            # Simple version - just pass hub_url
            _hub_client = HubClient(hub_url, app=app)
            _hub_client.connect()
            app.logger.info("✅ Hub Client connected")

            # ========================================================================
            # 3. REGISTER AS MAIN MODULE
            # ========================================================================
            _hub_client.register_as_main_module(
                app.config['MODULE_ID'],
                app.config['MODULE_NAME']
                # required_plugins=[{'id': 'timer-plugin', 'name': 'Timer Plugin'}],
                # required_plugins=app.config['REQUIRED_PLUGINS'],
                # subscribe_classes=app.config['SUBSCRIBE_CLASSES']
            )
            time.sleep(0.5)  # Give HUB time to process registration
            app.logger.info("✅ Registered as main module")

            # ========================================================================
            # 4. DECLARE REQUIRED PLUGINS → HUB WILL START THEM!
            # ========================================================================
            plugin_list = current_app.config['REQUIRED_PLUGINS']
            _hub_client.declare_required_plugins(plugin_list)

            app.logger.info("=" * 60)
            app.logger.info(f"✅ Declared {len(plugin_list)} required plugins to HUB")
            app.logger.info("   🚀 HUB WILL START PLUGINS AUTOMATICALLY")
            app.logger.info("=" * 60)

            # Wait a bit for plugins to start
            time.sleep(1.0)

            subscribe_classes = app.config['SUBSCRIBE_CLASSES']
            _hub_client.subscribe_to_classes(subscribe_classes)

            # ========================================================================
            # 5. OTHER MANAGERS (Lazy Initialization)
            # ========================================================================
            app.logger.info("✅ Manager initialization complete")
            app.logger.info("   Timer/Game/Recorder managers will init on first use")

            _initialized = True

        except Exception as e:
            app.logger.error(
                f"❌ Failed to initialize managers: {e}",
                exc_info=True
            )
            raise


# def get_plugin_manager():
#     """Get Plugin Manager instance"""
#     return _plugin_manager


def get_hub_client():
    """Get Hub Client instance (lazy initialization)"""
    global _hub_client

    if _hub_client is None:
        from app.managers.hub_client import HubClient
        _hub_client = HubClient(current_app.config['HUB_HOST'], current_app)
        current_app.logger.info("✅ Timer Manager initialized (lazy)")
    return _hub_client


def get_timer_manager():
    """Get Timer Manager instance (lazy initialization)"""
    global _timer_manager

    if _timer_manager is None:
        from app.managers.timer_manager import TimerManager
        _timer_manager = TimerManager(get_hub_client())
        current_app.logger.info("✅ Timer Manager initialized (lazy)")

    return _timer_manager


def get_current_game_manager():
    """Get Game Manager instance (lazy initialization)"""
    global _current_game_manager

    if _current_game_manager is None:
        from app.managers.current_game_manager import CurrentGameManager
        _current_game_manager = CurrentGameManager(get_hub_client())
        current_app.logger.info("✅ Game Manager initialized (lazy)")

    return _current_game_manager


def get_recorder_manager():
    """Get Recorder Manager instance (lazy initialization)"""
    global _recorder_manager

    if _recorder_manager is None:
        from app.managers.recorder_manager import RecorderManager
        _recorder_manager = RecorderManager(get_hub_client())
        current_app.logger.info("✅ Recorder Manager initialized (lazy)")

    return _recorder_manager


def shutdown_all_managers():
    """
    Shutdown all managers

    Note: We DON'T stop plugin processes - HUB manages them!
    """
    # global _plugin_manager, _hub_client, _current_game_manager
    global _hub_client, _current_game_manager
    global _recorder_manager, _timer_manager, _initialized

    current_app.logger.info("=" * 60)
    current_app.logger.info("SHUTTING DOWN MANAGERS")
    current_app.logger.info("=" * 60)

    # Disconnect from HUB
    if _hub_client is None:
        _hub_client = get_hub_client()
    current_app.logger.info("Disconnecting from HUB...")
    _hub_client.disconnect()
    current_app.logger.info("✅ Disconnected from HUB")

    # Clear references
    # _plugin_manager = None
    _hub_client = None
    _current_game_manager = None
    _recorder_manager = None
    _timer_manager = None
    _initialized = False

    current_app.logger.info("=" * 60)
    current_app.logger.info("✅ Managers shutdown complete")
    current_app.logger.info("=" * 60)


__all__ = [
    'initialize_all_managers',
    # 'get_plugin_manager',
    'get_hub_client',
    'get_current_game_manager',
    'get_recorder_manager',
    'get_timer_manager',
    'shutdown_all_managers'
]

# Direct imports for simple managers (no dependencies on HUB)
from app.managers.team_manager import TeamManager
from app.managers.season_manager import SeasonManager
from app.managers.league_manager import LeagueManager
from app.managers.game_manager import GameManager
from app.managers.team_scraper_manager import TeamScraperManager
from app.managers.camera_manager import CameraManager
from app.managers.period_manager import PeriodManager
from app.managers.game_camera_manager import GameCameraManager
from app.managers.penalty_manager import PenaltyManager
from app.managers.player_manager import PlayerManager
from app.managers.player_game_manager import PlayerGameManager
from app.managers.event_manager import EventManager
from app.managers.game_event_manager import GameEventManager
from app.managers.commentator_manager import CommentatorManager
from app.managers.game_commentator_manager import GameCommentatorManager
from app.managers.commentator_manager import CommentatorManager
from app.managers.game_commentator_manager import GameCommentatorManager
