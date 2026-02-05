import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"
    SOCKETIO_ASYNC_MODE = 'threading'

    MODULE_ID = 'futsal-nalf'
    MODULE_NAME = 'FUTSAL NALF'
    # HUB_HOST = 'broadcast-hub.local'
    HUB_HOST = 'ws://localhost:8080/ws'
    # HUB_HOST = 'broadcast-hub'
    # HUB_PORT = 8080
    APP_HOST = '0.0.0.0'
    APP_PORT = 8081

    REQUIRED_PLUGINS = ['timer-plugin', 'recorder-plugin']
    SUBSCRIBE_CLASSES = ['timer_update_receiver', 'timer_status_receiver']

    HUB_EXECUTABLE = '../../hub/hub.exe'
    PLUGINS_DIR = '../../plugins'


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
