"""Flask extensions — wspólna instancja db i socketio."""
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

db = SQLAlchemy()
socketio = SocketIO()
