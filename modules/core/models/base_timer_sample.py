"""BaseTimerSampleMixin — log próbek głównego timera okresu (elapsed_time_ms
w danym momencie ściennym), do zamiany "42:23 pierwszej połowy" na czas
ścienny (UTC).

Log zamiast pojedynczego stanu (GameTimer.sync_from_plugin() nadpisuje bieżący
stan bez zachowania historii) — dzięki temu pauzy same wychodzą z odstępu
próbek o tym samym elapsed_time_ms przy rosnącym occurred_at, bez potrzeby
osobnej logiki start/pauza/wznów.

occurred_at to czas odebrania sygnału przez serwer main-module (nie czas
zgłoszony przez timer-plugin) — z tego samego powodu co w
BaseCameraRecordingSegmentMixin: jeden wspólny zegar (serwera) zamiast
zależności od zgodności zegarów wielu urządzeń.

Częstotliwość zapisu jest throttlowana po stronie wywołującego
(TimerManager._maybe_record_timer_sample) — logujemy każdą zmianę stanu
(start/pauza/wznów) natychmiast, a w trakcie "running" najwyżej raz na kilka
sekund, żeby nie zalać tabeli tickami co 100ms.
"""
from core.extensions import db
from datetime import datetime, timedelta
from sqlalchemy.orm import declared_attr


class BaseTimerSampleMixin:

    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def period_id(cls):
        return db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=False, index=True)

    elapsed_time_ms = db.Column(db.Integer, nullable=False)
    state           = db.Column(db.String(20), nullable=False)
    occurred_at     = db.Column(db.DateTime, nullable=False, index=True)

    @declared_attr
    def period(cls):
        return db.relationship('Period')

    def __repr__(self):
        return (f'<TimerSample period_id={self.period_id} '
                f'{self.elapsed_time_ms}ms {self.state} @{self.occurred_at}>')

    @classmethod
    def last_for_period(cls, period_id):
        return (cls.query
                .filter_by(period_id=period_id)
                .order_by(cls.occurred_at.desc())
                .first())

    @classmethod
    def record(cls, period_id, elapsed_time_ms, state, occurred_at=None):
        row = cls(
            period_id=period_id,
            elapsed_time_ms=elapsed_time_ms,
            state=state,
            occurred_at=occurred_at or datetime.utcnow(),
        )
        db.session.add(row)
        db.session.commit()
        return row

    @classmethod
    def wall_clock_for_elapsed(cls, period_id, target_elapsed_ms):
        """
        Interpoluj czas ścienny dla zadanego elapsed_time_ms na podstawie
        najbliższych otaczających próbek. None jeśli brak jakichkolwiek
        próbek dla tego okresu.
        """
        before = (cls.query
                  .filter(cls.period_id == period_id, cls.elapsed_time_ms <= target_elapsed_ms)
                  .order_by(cls.elapsed_time_ms.desc())
                  .first())
        after = (cls.query
                 .filter(cls.period_id == period_id, cls.elapsed_time_ms >= target_elapsed_ms)
                 .order_by(cls.elapsed_time_ms.asc())
                 .first())

        if before is None and after is None:
            return None
        if before is None:
            return after.occurred_at
        if after is None:
            return before.occurred_at
        if before.id == after.id or before.elapsed_time_ms == after.elapsed_time_ms:
            return before.occurred_at

        span_elapsed = after.elapsed_time_ms - before.elapsed_time_ms
        span_wall_s  = (after.occurred_at - before.occurred_at).total_seconds()
        frac = (target_elapsed_ms - before.elapsed_time_ms) / span_elapsed
        return before.occurred_at + timedelta(seconds=span_wall_s * frac)


def get_timer_sample_model():
    """Zwraca konkretną klasę BaseTimerSampleMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'timer_samples'
                and issubclass(cls, BaseTimerSampleMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseTimerSampleMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_timer_sample_model()."
    )
