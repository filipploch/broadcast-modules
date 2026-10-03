"""Layout — moduł garbarnia."""
from core.models.base_layout import BaseLayoutMixin
from core.extensions import db


class Layout(BaseLayoutMixin, db.Model):
    __tablename__ = 'layouts'
