"""Camera Manager - handles CRUD operations for Camera model"""
from typing import List, Optional
from core.extensions import db
import logging

logger = logging.getLogger(__name__)

def _get_camera():
    from core.models.base_camera import get_camera_model
    return get_camera_model()

class CameraManager:
    """Manager for Camera CRUD operations"""

    def create_camera(self, name: str, brand: str, model: str,
                      cam_head_id: int = None, gopro_ssid: str = None,
                      gopro_password: str = None):
        try:
            Camera = _get_camera()
            camera = Camera(
                name=name,
                brand=brand,
                model=model,
                cam_head_id=cam_head_id or None,
                gopro_ssid=gopro_ssid or None,
                gopro_password=gopro_password or None,
            )
            db.session.add(camera)
            db.session.commit()
            logger.info(f"Created camera: {camera.name} ({camera.brand} {camera.model})")
            return camera
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating camera: {e}")
            return None

    def get_all_cameras(self):
        """Get all cameras"""
        Camera = _get_camera()
        return Camera.query.order_by(Camera.name).all()

    def get_camera_by_id(self, camera_id: int):
        """Get camera by ID"""
        Camera = _get_camera()
        return Camera.query.get(camera_id)

    def update_camera(self, camera_id: int, name: str = None, brand: str = None,
                     model: str = None, cam_head_id: int = None,
                     gopro_ssid: str = None, gopro_password: str = None,
                     clear_cam_head: bool = False):
        camera = self.get_camera_by_id(camera_id)
        if not camera:
            logger.warning(f"Camera with ID {camera_id} not found")
            return None

        try:
            if name is not None:
                camera.name = name
            if brand is not None:
                camera.brand = brand
            if model is not None:
                camera.model = model
            if clear_cam_head:
                camera.cam_head_id = None
            elif cam_head_id is not None:
                camera.cam_head_id = cam_head_id
            if gopro_ssid is not None:
                camera.gopro_ssid = gopro_ssid or None
            if gopro_password is not None:
                camera.gopro_password = gopro_password or None

            db.session.commit()
            logger.info(f"Updated camera ID {camera_id}")
            return camera

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating camera: {e}")
            return None

    def delete_camera(self, camera_id: int) -> bool:
        """
        Delete camera
        
        Note: This will also delete all GameCamera associations (cascade)

        Args:
            camera_id: Camera ID

        Returns:
            True if deleted, False if error
        """
        camera = self.get_camera_by_id(camera_id)
        if not camera:
            logger.warning(f"Camera with ID {camera_id} not found")
            return False

        try:
            db.session.delete(camera)
            db.session.commit()
            logger.info(f"Deleted camera: {camera.name}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting camera: {e}")
            return False
