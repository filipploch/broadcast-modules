from core.extensions import db
from core.models.base_helper_event_candidate import BaseHelperEventCandidateMixin


class HelperEventCandidate(BaseHelperEventCandidateMixin, db.Model):
    __tablename__ = 'helper_event_candidates'
