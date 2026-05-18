from core.models.base_shootout import BaseShootoutMixin
from core.extensions import db


class Shootout(BaseShootoutMixin, db.Model):
    __tablename__ = 'shootouts'
