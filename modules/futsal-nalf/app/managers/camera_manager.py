"""Camera Manager - handles CRUD operations for Camera model"""
from typing import List, Optional
from app.extensions import db
from app.models.camera import Camera
import logging

logger = logging.getLogger(__name__)


class CameraManager:
    """Manager for Camera CRUD operations"""

    def create_camera(self, name: str, brand: str, model: str) -> Optional[Camera]:
        """
        Create new camera

        Args:
            name: Camera name (e.g., "Main Camera", "Camera 1")
            brand: Camera brand (e.g., "Sony", "Canon")
            model: Camera model (e.g., "FX3", "C70")

        Returns:
            Camera object or None if error
        """
        try:
            camera = Camera(
                name=name,
                brand=brand,
                model=model
            )
            db.session.add(camera)
            db.session.commit()

            logger.info(f"Created camera: {camera.name} ({camera.brand} {camera.model})")
            return camera

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating camera: {e}")
            return None

    def get_all_cameras(self) -> List[Camera]:
        """Get all cameras"""
        return Camera.query.order_by(Camera.name).all()

    def get_camera_by_id(self, camera_id: int) -> Optional[Camera]:
        """Get camera by ID"""
        return Camera.query.get(camera_id)

    def update_camera(self, camera_id: int, name: str = None, brand: str = None, 
                     model: str = None) -> Optional[Camera]:
        """
        Update camera

        Args:
            camera_id: Camera ID
            name: New name (optional)
            brand: New brand (optional)
            model: New model (optional)

        Returns:
            Updated Camera object or None if error
        """
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
