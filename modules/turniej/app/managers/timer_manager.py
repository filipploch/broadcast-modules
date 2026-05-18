"""TimerManager — moduł turniej.

Timer liczony w górę (garbarnia-style): pause_at_limit=False.
Operator zatrzymuje ręcznie, czas doliczony naturalnie.
"""
from core.managers.timer_manager import TimerManager as _CoreTM


class TimerManager(_CoreTM):

    def create_game_timer(self, game_id, duration_minutes=15):
        return super().create_game_timer(
            game_id, duration_minutes=duration_minutes, pause_at_limit=False
        )
