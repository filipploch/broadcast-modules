from core.extensions import db
from core.models.base_helper_event_submission import BaseHelperEventSubmissionMixin


class HelperEventSubmission(BaseHelperEventSubmissionMixin, db.Model):
    __tablename__ = 'helper_event_submissions'
