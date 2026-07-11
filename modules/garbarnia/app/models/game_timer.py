"""GameTimer — moduł garbarnia.

Rozszerza BaseGameTimerMixin o pola dla timerów kar:
  - start_offset_ms  (czas startu kary względem głównego timera)
  - adjustment_ms    (ręczna korekta czasu kary)
"""
from core.extensions import db
from core.models.base_game_timer import BaseGameTimerMixin


class GameTimer(BaseGameTimerMixin, db.Model):
    __tablename__ = 'game_timers'

    start_offset_ms = db.Column(db.Integer, nullable=True)
    adjustment_ms   = db.Column(db.Integer, nullable=False, default=0)

    def penalty_remaining_ms(self, main_elapsed_ms: int) -> int:
        """Pozostały czas kary obliczony z głównego timera."""
        if self.start_offset_ms is None or self.limit_ms is None:
            raise ValueError(
                f'GameTimer id={self.id}: start_offset_ms lub limit_ms nie są ustawione'
            )
        elapsed = main_elapsed_ms - self.start_offset_ms + self.adjustment_ms
        return min(self.limit_ms, max(0, self.limit_ms - elapsed))
