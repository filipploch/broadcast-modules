"""TimerManager — moduł futsal-nalf.

Dziedziczy CoreTimerManager. Nadpisuje create_game_timer —
futsal nie używa pause_at_limit (timer odlicza w górę).
"""
from core.managers.timer_manager import TimerManager as _CoreTM


class TimerManager(_CoreTM):

    def create_game_timer(self, game_id, duration_minutes=20):
        """Futsal: okresy 20-minutowe, timer zatrzymuje się na limicie."""
        return super().create_game_timer(
            game_id, duration_minutes=duration_minutes, pause_at_limit=True
        )
