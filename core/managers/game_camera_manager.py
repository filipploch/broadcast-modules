"""GameCamera Manager - handles camera assignments for games"""
from typing import List, Optional
from core.extensions import db
from core.models.game_camera import GameCamera, HDMI_TO_DEVICE, HDMI_DEFAULT_LOCATION, VALID_HDMI_INPUTS
from core.models.game import Game
from core.models.camera import Camera
import logging

logger = logging.getLogger(__name__)


class GameCameraManager:
    """Manager for GameCamera CRUD operations"""

    def assign_camera_to_game(self, game_id: int, camera_id: int, hdmi_input: int,
                              location: str = None, is_motorized: bool = False) -> GameCamera:
        """
        Przypisz kamerę do meczu.

        Args:
            game_id:      ID meczu
            camera_id:    ID fizycznej kamery (tabela cameras)
            location:     Opis słowny miejsca ustawienia kamery (np. "Za bramką północną").
                          Jeśli None, zostanie użyta predefiniowana nazwa dla danego slotu
                          z HDMI_DEFAULT_LOCATION (np. hdmi_input=1 → "Główna").
            hdmi_input:   Numer wejścia HDMI karty przechwytującej (1–4).
                          Slot 1 = kamera główna.
            is_motorized: Czy kamera jest motoryczna

        Returns:
            Nowy obiekt GameCamera

        Raises:
            ValueError: mecz/kamera nie istnieje, naruszenie unikalności, zły numer slotu
        """
        # Walidacja zakresu slotu HDMI
        if hdmi_input not in VALID_HDMI_INPUTS:
            raise ValueError(
                f"Nieprawidłowy numer wejścia HDMI: {hdmi_input}. "
                f"Dozwolone wartości: {list(VALID_HDMI_INPUTS)}"
            )

        # Walidacja istnienia meczu
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Walidacja istnienia kamery
        camera = Camera.query.get(camera_id)
        if not camera:
            raise ValueError(f"Kamera o ID {camera_id} nie istnieje")

        # Zastosuj domyślną nazwę lokalizacji jeśli operator nie podał własnej
        if not location:
            location = HDMI_DEFAULT_LOCATION[hdmi_input]

        # Limit 4 kamer per mecz
        assigned_count = GameCamera.query.filter_by(game_id=game_id).count()
        if assigned_count >= 4:
            raise ValueError("Do meczu można przypisać maksymalnie 4 kamery")

        # Sprawdzenie unikalności: ta kamera już przypisana do tego meczu?
        if GameCamera.query.filter_by(game_id=game_id, camera_id=camera_id).first():
            raise ValueError(f"Kamera '{camera.name}' jest już przypisana do tego meczu")

        # Sprawdzenie unikalności: ten slot HDMI już zajęty?
        if GameCamera.query.filter_by(game_id=game_id, hdmi_input=hdmi_input).first():
            device = HDMI_TO_DEVICE[hdmi_input]
            raise ValueError(
                f"Wejście HDMI {hdmi_input} ({device}) jest już zajęte w tym meczu"
            )

        try:
            game_camera = GameCamera(
                game_id=game_id,
                camera_id=camera_id,
                location=location,
                hdmi_input=hdmi_input,
                is_motorized=is_motorized,
            )
            db.session.add(game_camera)
            db.session.commit()

            logger.info(
                f"Przypisano kamerę '{camera.name}' do meczu {game_id} "
                f"(lokalizacja: '{location}', HDMI {hdmi_input} → {game_camera.device_name})"
            )
            return game_camera

        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd przypisania kamery do meczu: {e}")
            raise

    def get_cameras_for_game(self, game_id: int) -> List[GameCamera]:
        """Zwróć wszystkie kamery przypisane do meczu, posortowane po numerze slotu HDMI."""
        return (GameCamera.query
                .filter_by(game_id=game_id)
                .order_by(GameCamera.hdmi_input)
                .all())

    def get_main_camera(self, game_id: int) -> Optional[GameCamera]:
        """Zwróć kamerę główną meczu (slot HDMI 1), lub None jeśli nie przypisana."""
        return GameCamera.query.filter_by(game_id=game_id, hdmi_input=1).first()

    def get_game_camera_by_id(self, game_camera_id: int) -> Optional[GameCamera]:
        """Zwróć GameCamera po ID."""
        return GameCamera.query.get(game_camera_id)

    def update_game_camera(self, game_camera_id: int, location: str = None,
                           hdmi_input: int = None,
                           is_motorized: bool = None) -> GameCamera:
        """
        Zaktualizuj przypisanie kamery.

        Args:
            game_camera_id: ID rekordu GameCamera
            location:       Nowy opis lokalizacji (opcjonalny)
            hdmi_input:     Nowy numer slotu HDMI (opcjonalny)
            is_motorized:   Nowa wartość flagi motorycznej (opcjonalna)

        Returns:
            Zaktualizowany obiekt GameCamera

        Raises:
            ValueError: rekord nie istnieje, nowy slot zajęty, zły numer slotu
        """
        game_camera = self.get_game_camera_by_id(game_camera_id)
        if not game_camera:
            raise ValueError(f"GameCamera o ID {game_camera_id} nie istnieje")

        try:
            if location is not None:
                game_camera.location = location

            if hdmi_input is not None and hdmi_input != game_camera.hdmi_input:
                if hdmi_input not in VALID_HDMI_INPUTS:
                    raise ValueError(
                        f"Nieprawidłowy numer wejścia HDMI: {hdmi_input}. "
                        f"Dozwolone wartości: {list(VALID_HDMI_INPUTS)}"
                    )
                existing = GameCamera.query.filter_by(
                    game_id=game_camera.game_id,
                    hdmi_input=hdmi_input,
                ).first()
                if existing:
                    device = HDMI_TO_DEVICE[hdmi_input]
                    raise ValueError(
                        f"Wejście HDMI {hdmi_input} ({device}) jest już zajęte w tym meczu"
                    )
                game_camera.hdmi_input = hdmi_input

            if is_motorized is not None:
                game_camera.is_motorized = is_motorized

            db.session.commit()
            logger.info(f"Zaktualizowano GameCamera ID {game_camera_id}")
            return game_camera

        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd aktualizacji GameCamera: {e}")
            raise

    def remove_camera_from_game(self, game_camera_id: int) -> bool:
        """
        Usuń przypisanie kamery z meczu.

        Returns:
            True jeśli usunięto, False jeśli rekord nie istniał
        """
        game_camera = self.get_game_camera_by_id(game_camera_id)
        if not game_camera:
            logger.warning(f"GameCamera o ID {game_camera_id} nie istnieje")
            return False

        try:
            db.session.delete(game_camera)
            db.session.commit()
            logger.info(f"Usunięto GameCamera ID {game_camera_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Błąd usuwania GameCamera: {e}")
            return False

    def get_available_hdmi_inputs(self, game_id: int) -> List[int]:
        """
        Zwróć listę wolnych slotów HDMI dla danego meczu.

        Returns:
            Lista numerów slotów HDMI (1–4) które nie są jeszcze zajęte.
        """
        taken = {
            gc.hdmi_input
            for gc in GameCamera.query.filter_by(game_id=game_id).all()
        }
        return [slot for slot in VALID_HDMI_INPUTS if slot not in taken]