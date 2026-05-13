"""GamePlayerManager — moduł futsal-nalf.

Dziedziczy CoreGamePlayerManager z core.
Nie nadpisuje żadnych metod — model GamePlayer futsalu
ma te same pola co Base (is_goalkeeper, is_captain).
"""
from core.managers.game_player_manager import GamePlayerManager as _CoreGPM


class GamePlayerManager(_CoreGPM):
    """GamePlayerManager dla futsal-nalf — bez rozszerzeń względem core."""
    pass
