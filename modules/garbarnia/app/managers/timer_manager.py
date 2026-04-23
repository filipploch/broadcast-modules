"""TimerManager — moduł garbarnia.

Dziedziczy CoreTimerManager. Nadpisuje create_game_timer —
piłka nożna: timer odlicza w dół (pause_at_limit=False,
metadata zawiera pause_at_limit=False dla poprawnego odczytu
przez on_timer_created w hub_client).
"""
from core.managers.timer_manager import TimerManager as _CoreTM


class TimerManager(_CoreTM):

    def create_game_timer(self, game_id, duration_minutes=40):
        """Garbarnia: pause_at_limit=False + zapisane w metadata."""
        return super().create_game_timer(
            game_id, duration_minutes=duration_minutes, pause_at_limit=False
        )
