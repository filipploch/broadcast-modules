from core.extensions import db
from core.models.base_game_timer import BaseGameTimerMixin
from datetime import datetime

class GameTimer(BaseGameTimerMixin, db.Model):
    __tablename__ = 'game_timers'

    start_offset_ms = db.Column(db.Integer, nullable=True)

    adjustment_ms   = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        d = super().to_dict()
        d['start_offset_ms'] = self.start_offset_ms
        d['adjustment_ms']   = self.adjustment_ms
        d['limit_ms']        = self.limit_ms
        return d

    def penalty_remaining_ms(self, main_elapsed_ms: int) -> int:
        """Pozostały czas kary obliczony z głównego timera."""
        if self.start_offset_ms is None or self.limit_ms is None:
            raise ValueError(
                f'GameTimer id={self.id}: start_offset_ms lub limit_ms nie są ustawione'
            )
        elapsed = main_elapsed_ms - self.start_offset_ms + self.adjustment_ms
        return min(self.limit_ms, max(0, self.limit_ms - elapsed))
