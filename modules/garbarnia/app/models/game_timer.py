"""GameTimer — moduł futsal-nalf.

Rozszerza BaseGameTimer o pola specyficzne dla timerów kar:
  - start_offset_ms: pozycja głównego timera w momencie nałożenia kary
  - adjustment_ms:   suma ręcznych korekt (+/-)

Używane w architekturze derived-variable gdzie czas kary jest obliczany
z głównego timera zamiast osobnego timera w pluginie.
"""
from core.extensions import db
from core.models.base_game_timer import BaseGameTimer
from datetime import datetime


class GameTimer(BaseGameTimer):
    __tablename__ = 'game_timers'

    # ── Futsal-specific (derived-variable penalty timers) ─────────────────────
    start_offset_ms = db.Column(db.Integer, nullable=True)
    adjustment_ms   = db.Column(db.Integer, nullable=False, default=0)

    def penalty_remaining_ms(self, main_elapsed_ms: int) -> int:
        """Pozostały czas kary obliczony z głównego timera."""
        if self.start_offset_ms is None or self.limit_ms is None:
            raise ValueError(
                f'GameTimer id={self.id}: start_offset_ms lub limit_ms nie są ustawione'
            )
        elapsed = main_elapsed_ms - self.start_offset_ms + self.adjustment_ms
        return max(0, self.limit_ms - elapsed)

    def apply_adjustment(self, delta_ms: int):
        """Nadpisuje BaseGameTimer — aktualizuje adjustment_ms."""
        self.adjustment_ms += delta_ms
        self.updated_at = datetime.utcnow()

    def to_dict(self):
        d = super().to_dict()
        d.update({
            'start_offset_ms': self.start_offset_ms,
            'adjustment_ms':   self.adjustment_ms,
        })
        return d
