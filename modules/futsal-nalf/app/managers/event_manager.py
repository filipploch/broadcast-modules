"""Event Manager - handles CRUD operations for Event model"""
from typing import List, Optional
from app.extensions import db
from app.models.event import Event
import logging

logger = logging.getLogger(__name__)


class EventManager:
    """Manager for Event CRUD operations"""

    def create_event(self, name: str, short_name: str,
                    is_reported: bool = False,
                    color: str = '#FFFFFF',
                    filter_class: str = None,
                    player_from_opponent: bool = False,
                    image_path: str = None) -> Optional[Event]:
        """
        Create new event type

        Args:
            name: Event name (e.g., "Bramka", "Żółta kartka")
            short_name: Short name (e.g., "G", "YC")
            is_reported: Whether event requires team/player assignment (default: False)
            image_path: Path to event icon (optional)

        Returns:
            Event object or None if error
        """
        try:
            event = Event(
                name=name,
                short_name=short_name,
                is_reported=is_reported,
                color=color,
                filter_class=filter_class,
                player_from_opponent=player_from_opponent,
                image_path=image_path
            )
            db.session.add(event)
            db.session.commit()

            logger.info(f"Created event: {event.name} (reported: {event.is_reported})")
            return event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating event: {e}")
            return None

    def get_all_events(self) -> List[Event]:
        """Get all event types"""
        return Event.query.order_by(Event.id).all()

    def get_reported_events(self) -> List[Event]:
        """Get events that require team/player assignment"""
        return Event.query.filter_by(is_reported=True).order_by(Event.name).all()

    def get_system_events(self) -> List[Event]:
        """Get system events (no team/player assignment)"""
        return Event.query.filter_by(is_reported=False).order_by(Event.name).all()

    def get_event_by_id(self, event_id: int) -> Optional[Event]:
        """Get event by ID"""
        return Event.query.get(event_id)

    def get_event_by_short_name(self, short_name: str) -> Optional[Event]:
        """Get event by short name"""
        return Event.query.filter_by(short_name=short_name).first()

    def update_event(self, event_id: int, name: str = None,
                    short_name: str = None, is_reported: bool = None,
                    color: str = None, filter_class: str = None,
                    player_from_opponent: bool = None,
                    image_path: str = None) -> Optional[Event]:
        """
        Update event type

        Args:
            event_id: Event ID
            name: New name (optional)
            short_name: New short name (optional)
            is_reported: New reported status (optional)
            image_path: New image path (optional)

        Returns:
            Updated Event object or None if error
        """
        event = self.get_event_by_id(event_id)
        if not event:
            logger.warning(f"Event with ID {event_id} not found")
            return None

        try:
            if name is not None:
                event.name = name
            if short_name is not None:
                event.short_name = short_name
            if is_reported is not None:
                event.is_reported = is_reported
            if color is not None:
                event.color = color
            if filter_class is not None:
                event.filter_class = filter_class or None  # '' → None
            if player_from_opponent is not None:
                event.player_from_opponent = player_from_opponent
            if image_path is not None:
                event.image_path = image_path

            db.session.commit()
            logger.info(f"Updated event ID {event_id}")
            return event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating event: {e}")
            return None

    def delete_event(self, event_id: int) -> bool:
        """
        Delete event type
        
        Note: This will also delete all GameEvent occurrences (cascade)

        Args:
            event_id: Event ID

        Returns:
            True if deleted, False if error
        """
        event = self.get_event_by_id(event_id)
        if not event:
            logger.warning(f"Event with ID {event_id} not found")
            return False

        try:
            event_name = event.name
            db.session.delete(event)
            db.session.commit()
            logger.info(f"Deleted event: {event_name}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting event: {e}")
            return False

    def create_default_events(self) -> List[Event]:
        """
        Create default event types for futsal
        
        Returns:
            List of created Event objects
        """
        default_events = [
            # Reported events (require team/player)
            {"name": "Bramka", "short_name": "G", "is_reported": True, "color": "#69ffa7", "filter_class": "goal"},
            {"name": "Bramka samobójcza", "short_name": "OG", "is_reported": True, "color": "#f88f8f", "filter_class": "goal", "player_from_opponent": True},
            {"name": "Żółta kartka", "short_name": "YC", "is_reported": True, "color": "#f3ec12", "filter_class": "yellow_card"},
            {"name": "Czerwona kartka", "short_name": "RC", "is_reported": True, "color": "#ff1900", "filter_class": "red_card"},
            {"name": "Faul", "short_name": "F", "is_reported": True, "color": "#f77e1a", "filter_class": "foul"},
            {"name": "Obrona", "short_name": "S", "is_reported": False, "color": "#8e44ad", "filter_class": "save", "player_from_opponent": True},
            {"name": "Pudło", "short_name": "M", "is_reported": False, "color": "#37d3ce", "filter_class": "miss"},
            {"name": "VAR", "short_name": "V", "is_reported": False, "color": "#5454e2", "filter_class": "var"},
            {"name": "HAHAHA", "short_name": "xD", "is_reported": False, "color": "#7c7c7c", "filter_class": None},
            {"name": "BUM", "short_name": "##", "is_reported": False, "color": "#3c3c3c", "filter_class": None},
        ]

        created = []
        for event_data in default_events:
            # Check if already exists
            existing = self.get_event_by_short_name(event_data['short_name'])
            if existing:
                logger.info(f"Event '{event_data['name']}' already exists")
                continue

            event = self.create_event(**event_data)
            if event:
                created.append(event)

        logger.info(f"Created {len(created)} default events")
        return created
