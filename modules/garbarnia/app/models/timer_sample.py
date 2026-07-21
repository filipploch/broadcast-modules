from core.extensions import db
from core.models.base_timer_sample import BaseTimerSampleMixin


class TimerSample(BaseTimerSampleMixin, db.Model):
    __tablename__ = 'timer_samples'
