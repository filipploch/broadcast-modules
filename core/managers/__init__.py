"""
core.managers — infrastrukturalne managery wspólne dla wszystkich modułów.

Każdy moduł (futsal-nalf, football, ...) importuje te funkcje
w swoim app/managers/__init__.py i może je rozszerzać.
"""
from flask import current_app
import threading
import time

# ── Globalne singletony ───────────────────────────────────────────────────────
_hub_client           = None
_timer_manager        = None
_recorder_manager     = None
_obs_ws_manager       = None
_sequence_manager     = None
_plugin_manager       = None
_current_game_manager = None
_game_event_manager   = None
_replay_export_manager = None
_initialization_lock  = threading.Lock()
_initialized          = False


def initialize_core_managers(app):
    """
    Inicjalizuje infrastrukturalne managery wspólne dla wszystkich modułów.
    Wywoływana z app/__init__.py każdego modułu w wątku tła.

    Kroki:
      1. HubClient — połączenie z hubem
      2. Rejestracja jako main_module
      3. Deklaracja wymaganych pluginów → hub je startuje
      4. Subskrypcja klas wiadomości
      5. Pozostałe managery lazy-init przy pierwszym użyciu
    """
    global _hub_client, _timer_manager, _recorder_manager, _obs_ws_manager, \
           _sequence_manager, _plugin_manager, _current_game_manager, \
           _replay_export_manager, _game_event_manager, _initialized

    with _initialization_lock:
        if _initialized:
            app.logger.warning("Core managers already initialized")
            return

        app.logger.info("=" * 60)
        app.logger.info("INITIALIZING CORE MANAGERS")
        app.logger.info("=" * 60)

        try:
            from core.managers.hub_client import HubClient

            hub_url     = app.config['HUB_HOST']
            app.logger.info(f"Connecting to HUB: {hub_url}")

            _hub_client = HubClient(hub_url, app=app)
            _hub_client.connect()
            app.logger.info("✅ Hub Client connected")

            _hub_client.register_as_main_module(
                app.config['MODULE_ID'],
                app.config['MODULE_NAME']
            )
            time.sleep(0.5)
            app.logger.info("✅ Registered as main module")

            plugin_list = app.config['REQUIRED_PLUGINS']
            _hub_client.declare_required_plugins(plugin_list)
            app.logger.info(f"✅ Declared {len(plugin_list)} required plugins")

            time.sleep(1.0)

            _hub_client.subscribe_to_classes(app.config['SUBSCRIBE_CLASSES'])

            _initialized = True
            app.logger.info("✅ Core managers initialization complete")

        except Exception as e:
            app.logger.error(f"❌ Failed to initialize core managers: {e}",
                             exc_info=True)
            raise


# ── Lazy getters ──────────────────────────────────────────────────────────────

def get_hub_client():
    global _hub_client
    if _hub_client is None:
        from core.managers.hub_client import HubClient
        _hub_client = HubClient(current_app.config['HUB_HOST'], current_app)
    return _hub_client


def get_timer_manager():
    global _timer_manager
    if _timer_manager is None:
        from core.managers.timer_manager import TimerManager
        _timer_manager = TimerManager(get_hub_client())
        current_app.logger.info("✅ Timer Manager initialized (lazy)")
    return _timer_manager


def get_recorder_manager():
    global _recorder_manager
    if _recorder_manager is None:
        from core.managers.recorder_manager import RecorderManager
        _recorder_manager = RecorderManager(get_hub_client())
        current_app.logger.info("✅ Recorder Manager initialized (lazy)")
    return _recorder_manager


def get_obs_ws_manager():
    global _obs_ws_manager
    if _obs_ws_manager is None:
        from core.managers.obs_ws_manager import ObsWsManager
        _obs_ws_manager = ObsWsManager(get_hub_client())
        current_app.logger.info("✅ OBS WS Manager initialized (lazy)")
    return _obs_ws_manager


def get_sequence_manager():
    global _sequence_manager
    if _sequence_manager is None:
        from core.managers.sequence_manager import SequenceManager
        _sequence_manager = SequenceManager(
            get_hub_client(),
            current_app.config['SEQUENCES_PATH']
        )
        current_app.logger.info("✅ Sequence Manager initialized (lazy)")
    return _sequence_manager


def get_plugin_manager():
    global _plugin_manager
    if _plugin_manager is None:
        from core.managers.plugin_manager import PluginManager
        _plugin_manager = PluginManager(get_hub_client())
        current_app.logger.info("✅ Plugin Manager initialized (lazy)")
    return _plugin_manager


def get_current_game_manager():
    global _current_game_manager
    if _current_game_manager is None:
        from core.managers.current_game_manager import CurrentGameManager
        _current_game_manager = CurrentGameManager(get_hub_client())
        current_app.logger.info("✅ Current Game Manager initialized (lazy)")
    return _current_game_manager


def get_replay_export_manager():
    global _replay_export_manager
    if _replay_export_manager is None:
        from core.managers.replay_export_manager import ReplayExportManager
        from pathlib import Path
        data_dir = Path(current_app.config.get('REPLAY_EXPORT_DIR', 'app/data'))
        _replay_export_manager = ReplayExportManager(data_dir)
        current_app.logger.info("✅ Replay Export Manager initialized (lazy)")
    return _replay_export_manager


def shutdown_core_managers():
    """Rozłącza hub i zeruje wszystkie singletony."""
    global _hub_client, _timer_manager, _recorder_manager, _obs_ws_manager, \
           _sequence_manager, _plugin_manager, _current_game_manager, \
           _replay_export_manager, _initialized

    current_app.logger.info("Shutting down core managers...")

    if _hub_client is not None:
        _hub_client.disconnect()

    _hub_client           = None
    _timer_manager        = None
    _recorder_manager     = None
    _obs_ws_manager       = None
    _sequence_manager     = None
    _plugin_manager       = None
    _current_game_manager = None
    _replay_export_manager = None
    _game_event_manager   = None
    _initialized          = False

    current_app.logger.info("✅ Core managers shutdown complete")
