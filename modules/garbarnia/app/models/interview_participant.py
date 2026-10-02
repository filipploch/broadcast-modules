from core.extensions import db
from core.models.base_interview_participant import BaseInterviewParticipantMixin


class InterviewParticipant(BaseInterviewParticipantMixin, db.Model):
    __tablename__ = 'interview_participants'
