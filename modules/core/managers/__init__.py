"""
core.managers — infrastrukturalne managery wspólne dla wszystkich modułów.

Każdy moduł (futsal-nalf, football, ...) importuje te funkcje
w swoim app/managers/__init__.py i może je rozszerzać.
"""
from flask import current_app
import threading
import time

# ── Globalne singletony ───────────────────────────────────────────────────────
_hub_client            = None
_timer_manager         = None
_recorder_manager      = None
_obs_ws_manager        = None
_sequence_manager      = None
_plugin_manager        = None
_current_game_manager  = None
_game_event_manager    = None
_replay_export_manager = None
_controller_manager    = None  # ⭐ NOWY: integracja USB controllera
_servo_manager         = None  # pan/tilt MG90S servo heads
_gopro_manager         = None  # GoPro Hero 4 bridge
_helper_relay_client   = None  # połączenie WSS do apki pomocnika na Render
_helper_relay_manager  = None  # dedup/auto-reject/approve dla zgłoszeń pomocników
_initialization_lock   = threading.Lock()
_initialized           = False
_timer_manager_class   = None  # moduł może ustawić przed initialize_core_managers
_period_manager_class  = None  # moduł może ustawić przed initialize_core_managers



def initialize_core_managers(app):
    """
    Inicjalizuje infrastrukturalne managery wspólne dla wszystkich modułów.
    Wywoływana z app/__init__.py każdego modułu w wątku tła.

    Kroki:
      1. HubClient — połączenie z hubem
      2. Rejestracja jako main_module
      3. Deklaracja wymaganych pluginów → hub je startuje
      4. Subskrypcja klas wiadomości
      5. ControllerManager — łącznik controller-plugin ↔ replay-plugin
      6. Pozostałe managery lazy-init przy pierwszym użyciu
    """
    global _hub_client, _timer_manager, _recorder_manager, _obs_ws_manager, \
           _sequence_manager, _plugin_manager, _current_game_manager, \
           _replay_export_manager, _game_event_manager, _controller_manager, \
           _servo_manager, _gopro_manager, _helper_relay_client, \
           _helper_relay_manager, _initialized

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

            # ⭐ ControllerManager — eager init (musi istnieć zanim przyjdą
            # pierwsze sygnały od controller-plugin / replay-plugin).
            from core.managers.controller_manager import ControllerManager
            default_speed = app.config.get('REPLAY_DEFAULT_SPEED', 0.9)
            _controller_manager = ControllerManager(_hub_client, default_speed=default_speed)
            _controller_manager.attach_app(app)
            app.logger.info("✅ Controller Manager initialized")

            # HelperRelayManager — łącznik z apką pomocnika na Render (opcjonalny,
            # patrz docs/helper-app-design.md). Nigdy nie blokuje ani nie wywala
            # startu aplikacji — Render może jeszcze nie istnieć / spać.
            try:
                _helper_relay_manager = get_helper_relay_manager()
                if app.config.get('HELPER_RELAY_ENABLED', False):
                    get_helper_relay_client().connect()
                    app.logger.info("✅ Helper Relay Client — connecting (background)")
                else:
                    app.logger.info("Helper Relay wyłączony (HELPER_RELAY_ENABLED=False)")
            except Exception as e:
                app.logger.warning(f"Helper Relay init skipped: {e}")

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
        if _timer_manager_class is not None:
            cls = _timer_manager_class
        else:
            from core.managers.timer_manager import TimerManager
            cls = TimerManager
        _timer_manager = cls(get_hub_client())
    return _timer_manager


def get_period_manager():
    if _period_manager_class is not None:
        return _period_manager_class()
    from core.managers.period_manager import PeriodManager
    return PeriodManager()


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
            current_app.config['SEQUENCES_PATH'],
            app=current_app._get_current_object()
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


def get_controller_manager():
    """⭐ Singleton ControllerManager. Zwraca None jeśli initialize_core_managers
    jeszcze nie wykonało się (typowe w bardzo wczesnej fazie startu)."""
    global _controller_manager
    return _controller_manager


def get_servo_manager():
    global _servo_manager
    if _servo_manager is None:
        from core.managers.servo_manager import ServoManager
        _servo_manager = ServoManager(get_hub_client())
        current_app.logger.info("✅ Servo Manager initialized (lazy)")
    return _servo_manager


def get_gopro_manager():
    global _gopro_manager
    if _gopro_manager is None:
        from core.managers.gopro_manager import GoProManager
        _gopro_manager = GoProManager(get_hub_client())
        current_app.logger.info("✅ GoPro Manager initialized (lazy)")
    return _gopro_manager


def get_helper_relay_client():
    global _helper_relay_client
    if _helper_relay_client is None:
        from core.managers.helper_relay_client import HelperRelayClient
        _helper_relay_client = HelperRelayClient(
            relay_url=current_app.config.get('HELPER_RELAY_URL'),
            token=current_app.config.get('HELPER_RELAY_TOKEN'),
            app=current_app._get_current_object(),
            ping_interval_s=current_app.config.get('HELPER_RELAY_PING_INTERVAL_S', 300),
        )
        current_app.logger.info("✅ Helper Relay Client initialized (lazy)")
    return _helper_relay_client


def get_helper_relay_manager():
    global _helper_relay_manager
    if _helper_relay_manager is None:
        from core.managers.helper_relay_manager import HelperRelayManager
        client = get_helper_relay_client() if current_app.config.get('HELPER_RELAY_ENABLED', False) else None
        _helper_relay_manager = HelperRelayManager(relay_client=client)
        current_app.logger.info("✅ Helper Relay Manager initialized (lazy)")
    return _helper_relay_manager


def shutdown_core_managers():
    """Rozłącza hub i zeruje wszystkie singletony."""
    global _hub_client, _timer_manager, _recorder_manager, _obs_ws_manager, \
           _sequence_manager, _plugin_manager, _current_game_manager, \
           _replay_export_manager, _controller_manager, _helper_relay_client, \
           _helper_relay_manager, _initialized

    current_app.logger.info("Shutting down core managers...")

    if _hub_client is not None:
        _hub_client.disconnect()
    if _helper_relay_client is not None:
        _helper_relay_client.disconnect()

    _hub_client            = None
    _timer_manager         = None
    _recorder_manager      = None
    _obs_ws_manager        = None
    _sequence_manager      = None
    _plugin_manager        = None
    _current_game_manager  = None
    _replay_export_manager = None
    _game_event_manager    = None
    _controller_manager    = None
    _servo_manager         = None
    _gopro_manager         = None
    _helper_relay_client   = None
    _helper_relay_manager  = None
    _initialized           = False

    current_app.logger.info("✅ Core managers shutdown complete")