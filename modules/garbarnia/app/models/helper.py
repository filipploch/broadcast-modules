from core.extensions import db
from core.models.base_helper import BaseHelperMixin


class Helper(BaseHelperMixin, db.Model):
    __tablename__ = 'helpers'
