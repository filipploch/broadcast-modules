"""
Rozszerzenia Flask dla modułu futsal-nalf.
Importuje instancje db i socketio z core — jeden obiekt w całej aplikacji.
"""
from core.extensions import db, socketio

__all__ = ['db', 'socketio']
