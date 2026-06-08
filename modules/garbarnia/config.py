import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"
    SOCKETIO_ASYNC_MODE = 'threading'

    MODULE_ID = 'main-module'
    MODULE_NAME = 'garbarnia'
    HUB_HOST = 'ws://localhost:8080/ws'
    APP_HOST = '0.0.0.0'
    APP_PORT = 8081

    SUBSCRIBE_CLASSES = ['timer_update_receiver', 'timer_state_receiver', 'obs_messages_receiver', 'servo_events', 'gopro_events']
    REQUIRED_PLUGINS = ['timer-plugin', 'recorder-plugin', 'obs-ws-plugin', 'replay-plugin', 'controller-plugin', 'cam-head-1']
    REPLAY_SCENE   = 'OUTPUT'   # scena OBS z źródłem Replay
    REPLAY_SOURCE  = 'Replay'   # nazwa źródła Window Capture mpv w OBS
    REPLAY_DEFAULT_SPEED = 0.9

    HUB_EXECUTABLE = '../../hub/hub.exe'
    PLUGINS_DIR = '../../plugins'
    SEQUENCES_PATH = f'{MODULE_NAME}/app/sequences/sequences.py'
    REPLAY_EXPORT_DIR = f'{MODULE_NAME}/app/data'
    OVERLAY_DIR = '../../hub/overlays/futsal-nalf'
    HUB_CSS_DIR = 'hub/overlays/futsal-nalf/css/'
    HUB_JS_DIR = 'hub/overlays/futsal-nalf/js/'
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


class DevelopmentConfig(Config):
    DEBUG = True
    # SQLALCHEMY_ECHO = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}