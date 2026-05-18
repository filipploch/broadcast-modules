from core.models.base_camera import BaseCameraMixin
from core.extensions import db

class Camera(BaseCameraMixin, db.Model):
    __tablename__ = 'cameras'
