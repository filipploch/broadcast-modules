"""GameGoProSetup — moduł garbarnia."""
from core.models.base_game_gopro_setup import BaseGameGoProSetupMixin
from core.extensions import db


class GameGoProSetup(BaseGameGoProSetupMixin, db.Model):
    __tablename__ = 'game_gopro_setups'
