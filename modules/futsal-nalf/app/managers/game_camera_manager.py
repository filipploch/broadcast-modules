"""GameCamera Manager - handles camera assignments for games"""
from typing import List, Optional
from app.extensions import db
from app.models.game_camera import GameCamera
from app.models.game import Game
from app.models.camera import Camera
import logging

logger = logging.getLogger(__name__)


class GameCameraManager:
    """Manager for GameCamera CRUD operations"""

    def assign_camera_to_game(self, game_id: int, camera_id: int, location: str,
                              is_motorized: bool = False) -> Optional[GameCamera]:
        """
        Assign a camera to a game at specific location

        Args:
            game_id: Game ID
            camera_id: Camera ID
            location: Camera location (e.g., "Main", "Side", "Behind Goal")
            is_motorized: Whether camera is motorized (default: False)

        Returns:
            GameCamera object or None if error

        Raises:
            ValueError if game/camera not found or unique constraints violated
        """
        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Validate camera exists
        camera = Camera.query.get(camera_id)
        if not camera:
            raise ValueError(f"Kamera o ID {camera_id} nie istnieje")

        # Check unique constraints
        existing_camera = GameCamera.query.filter_by(game_id=game_id, camera_id=camera_id).first()
        if existing_camera:
            raise ValueError(f"Kamera {camera.name} jest już przypisana do tego meczu")

        existing_location = GameCamera.query.filter_by(game_id=game_id, location=location).first()
        if existing_location:
            raise ValueError(f"Lokalizacja '{location}' jest już zajęta w tym meczu")

        try:
            game_camera = GameCamera(
                game_id=game_id,
                camera_id=camera_id,
                location=location,
                is_motorized=is_motorized
            )
            db.session.add(game_camera)
            db.session.commit()

            logger.info(f"Assigned camera {camera.name} to game {game_id} at location {location}")
            return game_camera

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning camera to game: {e}")
            raise

    def get_cameras_for_game(self, game_id: int) -> List[GameCamera]:
        """Get all cameras assigned to a game"""
        return GameCamera.query.filter_by(game_id=game_id).all()

    def get_game_camera_by_id(self, game_camera_id: int) -> Optional[GameCamera]:
        """Get GameCamera by ID"""
        return GameCamera.query.get(game_camera_id)

    def update_game_camera(self, game_camera_id: int, location: str = None,
                          is_motorized: bool = None) -> Optional[GameCamera]:
        """
        Update game camera assignment

        Args:
            game_camera_id: GameCamera ID
            location: New location (optional)
            is_motorized: New motorized setting (optional)

        Returns:
            Updated GameCamera object or None if error

        Raises:
            ValueError if location already taken
        """
        game_camera = self.get_game_camera_by_id(game_camera_id)
        if not game_camera:
            logger.warning(f"GameCamera with ID {game_camera_id} not found")
            return None

        try:
            # Check location uniqueness if updating location
            if location is not None and location != game_camera.location:
                existing = GameCamera.query.filter_by(
                    game_id=game_camera.game_id,
                    location=location
                ).first()
                if existing:
                    raise ValueError(f"Lokalizacja '{location}' jest już zajęta w tym meczu")
                game_camera.location = location

            if is_motorized is not None:
                game_camera.is_motorized = is_motorized

            db.session.commit()
            logger.info(f"Updated GameCamera ID {game_camera_id}")
            return game_camera

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating game camera: {e}")
            raise

    def remove_camera_from_game(self, game_camera_id: int) -> bool:
        """
        Remove camera assignment from game

        Args:
            game_camera_id: GameCamera ID

        Returns:
            True if removed, False if error
        """
        game_camera = self.get_game_camera_by_id(game_camera_id)
        if not game_camera:
            logger.warning(f"GameCamera with ID {game_camera_id} not found")
            return False

        try:
            db.session.delete(game_camera)
            db.session.commit()
            logger.info(f"Removed camera from game (GameCamera ID: {game_camera_id})")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing camera from game: {e}")
            return False

    def get_available_locations(self, game_id: int, predefined_locations: List[str] = None) -> List[str]:
        """
        Get available (not yet assigned) locations for a game
        
        Args:
            game_id: Game ID
            predefined_locations: List of predefined location names (optional)
        
        Returns:
            List of available location names
        """
        if predefined_locations is None:
            predefined_locations = [
                "Main", "Side Left", "Side Right", "Behind Goal Home",
                "Behind Goal Away", "Overhead", "Corner"
            ]

        # Get taken locations
        taken = GameCamera.query.filter_by(game_id=game_id).all()
        taken_locations = {gc.location for gc in taken}

        # Return available
        return [loc for loc in predefined_locations if loc not in taken_locations]
