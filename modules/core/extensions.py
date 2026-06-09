"""Flask extensions — wspólna instancja db, socketio i migrate."""
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_migrate import Migrate

db = SQLAlchemy()
socketio = SocketIO()
migrate = Migrate()
