import os

# Folder tego modułu (modules/<moduł>/): ścieżki plików modułu liczone od położenia plików, nie od bieżącego folderu startu
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"
    SOCKETIO_ASYNC_MODE = 'threading'

    MODULE_ID = 'main-module'
    MODULE_NAME = 'garbarnia'
    # BM_HUB_URL i BM_MODULE_PORT ustawia HUB, który uruchamia moduł (E2d1); bez nich wartości dotychczasowe
    HUB_HOST = os.environ.get('BM_HUB_URL') or 'ws://localhost:8080/ws'
    APP_HOST = '0.0.0.0'
    APP_PORT = int(os.environ.get('BM_MODULE_PORT') or 8081)

    SUBSCRIBE_CLASSES = ['timer_update_receiver', 'timer_state_receiver', 'obs_messages_receiver', 'servo_events', 'gopro_events']
    # BM_REQUIRED_PLUGINS=timer-plugin,... zawęża listę (próby na sucho z samym timer-pluginem); domyślnie pełna lista
    REQUIRED_PLUGINS = [p for p in os.environ.get('BM_REQUIRED_PLUGINS', '').split(',') if p] or ['timer-plugin', 'recorder-plugin', 'obs-ws-plugin', 'replay-plugin', 'controller-plugin', 'cam-head-1']
    REPLAY_SCENE   = 'OUTPUT'   # scena OBS z źródłem Replay
    REPLAY_SOURCE  = 'Replay'   # nazwa źródła Window Capture mpv w OBS
    REPLAY_DEFAULT_SPEED = 0.9

    HUB_EXECUTABLE = '../../hub/hub.exe'
    PLUGINS_DIR = '../../plugins'
    SEQUENCES_PATH = os.path.join(_MODULE_DIR, 'app', 'sequences', 'sequences.py')
    REPLAY_EXPORT_DIR = os.path.join(_MODULE_DIR, 'app', 'data')
    OVERLAY_DIR = '../../hub/overlays/garbarnia'
    HUB_CSS_DIR = 'hub/overlays/garbarnia/css/'
    HUB_JS_DIR = 'hub/overlays/garbarnia/js/'
    # Nazwa folderu overlayu w hubie (hub/overlays/<nazwa>/) — wysyłana w
    # sygnale apply_styling_class, żeby hub wiedział, którego folderu dotyczy
    # przełączenie stylu. Osobny klucz od OVERLAY_DIR (ścieżka względna z
    # modułu) — hub pracuje ze ścieżkami względnymi do SIEBIE, nie do modułu.
    OVERLAY_DIR_NAME = 'garbarnia'
    SPECIFIC_JS_FILE = f'modules/{MODULE_NAME}/static/specific.js'
    SPECIFIC_CSS_FILE = f'modules/{MODULE_NAME}/static/specific.css'
    TEMP_DIR = f'/data/temp/'

    # Czy zawodnik schodzący z boiska może wrócić do gry?
    #   False — dostaje ROLE_RETIRED  (nie może wrócić)
    #   True  — dostaje ROLE_SUBSTITUTE (może wejść ponownie)
    RETURN_CHANGES = False

    TIMER_DESC = False
    HAS_PENALTY_TIMERS = False

    MEDIA_CURSOR = None

    # Apka pomocnika realizatora (Render), patrz docs/helper-app-design.md.
    # Wyłączona domyślnie — apka jeszcze nie istnieje; gdy powstanie, ustawić
    # HELPER_RELAY_ENABLED=1 i podać prawdziwy URL/token przez zmienne środowiskowe.
    HELPER_RELAY_ENABLED = os.environ.get('HELPER_RELAY_ENABLED', '0') == '1'
    HELPER_RELAY_URL = os.environ.get('HELPER_RELAY_URL') or 'wss://REPLACE-ME.onrender.com/relay'
    HELPER_RELAY_TOKEN = os.environ.get('HELPER_RELAY_TOKEN') or ''
    HELPER_RELAY_PING_INTERVAL_S = 300
    HELPER_MATCH_TOLERANCE_S = 8

    # Lekki kanał REST do Helper App (osobny od HELPER_RELAY_* powyżej,
    # który jest zarezerwowany dla przyszłego WSS relay). Używany dziś tylko
    # przez funkcję "skład + trener" — moduł główny zawsze dzwoni wychodząco
    # (POST push kadry / GET pull propozycji), Render nigdy nie łączy się
    # do modułu głównego (ten jest za NAT-em).
    HELPER_APP_BASE_URL = os.environ.get('HELPER_APP_BASE_URL') or 'http://localhost:5001'
    HELPER_APP_REST_TOKEN = os.environ.get('HELPER_APP_REST_TOKEN') or ''


class DevelopmentConfig(Config):
    # Moduł uruchomiony przez HUB (BM_HUB_MANAGED=1) nie działa w trybie debug: debugger Werkzeuga drukuje na stderr
    # traceback ConnectionError po każdym zamknięciu połączenia websocket (engineio kończy je takim wyjątkiem celowo)
    DEBUG = os.environ.get('BM_HUB_MANAGED') != '1'
    # SQLALCHEMY_ECHO = True
    SQLALCHEMY_ECHO = False


class TestingConfig(Config):
    """Testy automatyczne (tests/modules): baza z BM_TEST_DATABASE_URL, bez startu menedżerów i połączenia z HUB-em."""
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('BM_TEST_DATABASE_URL') or 'sqlite:///:memory:'


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}