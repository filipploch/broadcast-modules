"""Period Manager - handles CRUD operations for Period model"""
from typing import List, Optional
from app.extensions import db
from app.models.period import Period
from app.models.game import Game
import logging

logger = logging.getLogger(__name__)


class PeriodManager:
    """Manager for Period CRUD operations"""

    def create_period(self, game_id: int, period_order: int, description: str,
                     limit_time: int = 1200000, pause_at_limit: bool = True,
                     auto_calculate_initial_time: bool = True) -> Optional[Period]:
        """
        Create new period for a game

        Args:
            game_id: Game ID
            period_order: Period order (1, 2, 3, etc.)
            description: Period description (e.g., "1. połowa", "2. połowa")
            limit_time: Time limit in milliseconds (default: 1200000 = 20 minutes)
            pause_at_limit: Whether to pause at time limit (default: True)
            auto_calculate_initial_time: Auto-calculate initial_time from previous periods (default: True)

        Returns:
            Period object or None if error

        Raises:
            ValueError if game not found or period_order already exists
        """
        # Validate game exists
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Check if period_order already exists for this game
        existing = Period.query.filter_by(game_id=game_id, period_order=period_order).first()
        if existing:
            raise ValueError(f"Część {period_order} już istnieje dla tego meczu")

        try:
            # Calculate initial_time
            if auto_calculate_initial_time:
                initial_time = Period.calculate_initial_time_for_period(game_id, period_order)
            else:
                initial_time = 0

            period = Period(
                game_id=game_id,
                period_order=period_order,
                description=description,
                initial_time=initial_time,
                limit_time=limit_time,
                pause_at_limit=pause_at_limit,
                status=Period.STATUS_NOT_STARTED
            )
            db.session.add(period)
            db.session.commit()

            logger.info(f"Created period {period_order} for game {game_id}: {description}")
            return period

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating period: {e}")
            raise

    def create_default_periods(self, game_id: int) -> List[Period]:
        """
        Create default 2 periods (halves) for a game
        
        Args:
            game_id: Game ID
        
        Returns:
            List of created Period objects
        """
        periods = []
        
        # First half
        period1 = self.create_period(
            game_id=game_id,
            period_order=1,
            description="1. połowa",
            limit_time=1200000,  # 20 minutes
            pause_at_limit=True
        )
        period1.update_timer_name()
        db.session.commit()
        periods.append(period1)
        
        # Second half
        period2 = self.create_period(
            game_id=game_id,
            period_order=2,
            description="2. połowa",
            limit_time=1200000,  # 20 minutes
            pause_at_limit=True
        )
        period2.update_timer_name()
        db.session.commit()
        periods.append(period2)
        
        logger.info(f"Created default 2 periods for game {game_id}")
        return periods

    def get_periods_by_game(self, game_id: int) -> List[Period]:
        """Get all periods for a game, ordered by period_order"""
        return Period.query.filter_by(game_id=game_id).order_by(Period.period_order).all()

    def get_period_by_id(self, period_id: int) -> Optional[Period]:
        """Get period by ID"""
        return Period.query.get(period_id)

    def update_period(self, period_id: int, description: str = None, 
                     limit_time: int = None, pause_at_limit: bool = None,
                     status: int = None) -> Optional[Period]:
        """
        Update period

        Args:
            period_id: Period ID
            description: New description (optional)
            limit_time: New time limit in milliseconds (optional)
            pause_at_limit: New pause setting (optional)
            status: New status (optional)

        Returns:
            Updated Period object or None if error
        """
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period with ID {period_id} not found")
            return None

        try:
            if description is not None:
                period.description = description
            if limit_time is not None:
                period.limit_time = limit_time
            if pause_at_limit is not None:
                period.pause_at_limit = pause_at_limit
            if status is not None:
                period.status = status

            db.session.commit()
            logger.info(f"Updated period ID {period_id}")
            return period

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating period: {e}")
            return None

    def set_period_status(self, period_id: int, status: int) -> Optional[Period]:
        """
        Set period status
        
        Args:
            period_id: Period ID
            status: New status (0=not started, 1=live, 2=finished)
        
        Returns:
            Updated Period object or None if error
        """
        return self.update_period(period_id, status=status)

    def start_period(self, period_id: int) -> Optional[Period]:
        """
        Start a period (set status to PENDING) and setup timers
        
        This method:
        1. Sets period status to PENDING
        2. Creates/updates main timer in Settings (state: idle, NOT started)
        3. Restores penalty timers if they exist (for periods > 1)
        4. Removes penalty timers with limit_reached status
        """
        from app.models.settings import Settings
        from app.managers import get_timer_manager
        
        period = self.set_period_status(period_id, Period.STATUS_PENDING)
        if not period:
            return None
        
        timer_manager = get_timer_manager()
        
        # Prepare main timer data
        main_timer_data = {
            "timer_id": period.main_timer_name,
            "timer_type": "independent",
            "initial_time": period.initial_time,
            "limit_time": period.limit_time,
            "pause_at_limit": period.pause_at_limit,
            "state": "idle",
            "metadata": {
                "description": period.description,
                "period": period.period_order,
                "timer_class": "main"
            }
        }
        
        # If this is not the first period, handle penalty timers
        if period.period_order > 1:
            # Remove penalty timers with limit_reached status
            Settings.remove_limit_reached_penalties()
            
            # Get remaining penalty timers
            current_timers = Settings.get_current_timers()
            remaining_penalties = current_timers.get("penalties", [])
            
            # Create main timer
            timer_manager.create_timer(
                timer_id=period.main_timer_name,
                timer_type="independent",
                initial_time=period.initial_time,
                limit_time=period.limit_time,
                pause_at_limit=period.pause_at_limit,
                metadata={
                    "description": period.description,
                    "period": period.period_order,
                    "timer_class": "main"
                }
            )
            
            # Update main timer in Settings
            Settings.update_main_timer(main_timer_data)
            
            # Recreate penalty timers as dependent
            for penalty in remaining_penalties:
                penalty_metadata = penalty.get("metadata", {})
                timer_manager.create_timer(
                    timer_id=penalty.get("timer_id"),
                    timer_type="dependent",
                    parent_id=period.main_timer_name,
                    initial_time=penalty.get("initial_time", 0),
                    limit_time=penalty.get("limit_time", 120000),
                    metadata=penalty_metadata
                )
        else:
            # First period - just create main timer
            timer_manager.create_timer(
                timer_id=period.main_timer_name,
                timer_type="independent",
                initial_time=period.initial_time,
                limit_time=period.limit_time,
                pause_at_limit=period.pause_at_limit,
                metadata={
                    "description": period.description,
                    "period": period.period_order,
                    "timer_class": "main"
                }
            )
            
            # Update main timer in Settings
            Settings.update_main_timer(main_timer_data)
        
        # DO NOT start the timer automatically - leave it in idle state
        # User will start it manually from UI
        
        return period

    def finish_period(self, period_id: int) -> Optional[Period]:
        """
        Finish a period (set status to FINISHED)
        
        This method:
        1. Stops all running timers
        2. Updates timer states in Settings with current elapsed times
        3. Sets period status to FINISHED
        """
        from app.models.settings import Settings
        from app.managers import get_timer_manager
        
        period = self.get_period_by_id(period_id)
        if not period:
            return None
        
        timer_manager = get_timer_manager()
        current_timers = Settings.get_current_timers()
        
        # Stop main timer if running
        main_timer = current_timers.get("main")
        if main_timer and main_timer.get("timer_id"):
            timer_state = timer_manager.get_timer_state(main_timer["timer_id"])
            if timer_state and timer_state.get("state") == "running":
                timer_manager.pause_timer(main_timer["timer_id"])
            
            # Update main timer with current state
            if timer_state:
                main_timer["state"] = timer_state.get("state", "paused")
                main_timer["initial_time"] = timer_state.get("elapsed_time", main_timer.get("initial_time", 0))
                Settings.update_main_timer(main_timer)
        
        # Stop and update all penalty timers
        penalties = current_timers.get("penalties", [])
        for i, penalty in enumerate(penalties):
            timer_id = penalty.get("timer_id")
            if timer_id:
                timer_state = timer_manager.get_timer_state(timer_id)
                if timer_state and timer_state.get("state") == "running":
                    timer_manager.pause_timer(timer_id)
                
                # Update penalty timer with current state
                if timer_state:
                    penalty["state"] = timer_state.get("state", "paused")
                    penalty["initial_time"] = timer_state.get("elapsed_time", penalty.get("initial_time", 0))
                    Settings.update_penalty_timer(timer_id, penalty)
        
        # Set period status to FINISHED
        return self.set_period_status(period_id, Period.STATUS_FINISHED)

    def delete_period(self, period_id: int) -> bool:
        """
        Delete period

        Args:
            period_id: Period ID

        Returns:
            True if deleted, False if error
        """
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period with ID {period_id} not found")
            return False

        try:
            db.session.delete(period)
            db.session.commit()
            logger.info(f"Deleted period {period.description} (ID: {period_id})")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting period: {e}")
            return False

    def get_current_period(self, game_id: int) -> Optional[Period]:
        """Get currently active period for a game"""
        return Period.query.filter_by(
            game_id=game_id,
            status=Period.STATUS_PENDING
        ).first()

    def update_period_score(self, period_id: int, home_goals: int, away_goals: int,
                           auto_sync: bool = True) -> Optional[Period]:
        """
        Update period score
        
        Args:
            period_id: Period ID
            home_goals: Home team goals in this period
            away_goals: Away team goals in this period
            auto_sync: Automatically sync to Game (default: True)
        
        Returns:
            Updated Period object or None if error
        """
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period with ID {period_id} not found")
            return None

        try:
            period.update_score(home_goals, away_goals)
            db.session.commit()
            
            if auto_sync:
                period.sync_to_game()
            
            logger.info(f"Updated period {period_id} score: {home_goals}:{away_goals}")
            return period

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating period score: {e}")
            return None

    def update_period_fouls(self, period_id: int, home_fouls: int, away_fouls: int,
                           auto_sync: bool = True) -> Optional[Period]:
        """
        Update period fouls
        
        Args:
            period_id: Period ID
            home_fouls: Home team fouls in this period
            away_fouls: Away team fouls in this period
            auto_sync: Automatically sync to Game (default: True)
        
        Returns:
            Updated Period object or None if error
        """
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period with ID {period_id} not found")
            return None

        try:
            period.update_fouls(home_fouls, away_fouls)
            db.session.commit()
            
            if auto_sync:
                period.sync_to_game()
            
            logger.info(f"Updated period {period_id} fouls: {home_fouls}:{away_fouls}")
            return period

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating period fouls: {e}")
            return None

    def increment_period_goal(self, period_id: int, team: str, auto_sync: bool = True) -> Optional[Period]:
        """
        Increment goal for a team in a period
        
        Args:
            period_id: Period ID
            team: 'home' or 'away'
            auto_sync: Automatically sync to Game (default: True)
        
        Returns:
            Updated Period object or None if error
        """
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period with ID {period_id} not found")
            return None

        try:
            if team.lower() == 'home':
                period.increment_home_goals()
            elif team.lower() == 'away':
                period.increment_away_goals()
            else:
                raise ValueError(f"Invalid team: {team}. Must be 'home' or 'away'")
            
            db.session.commit()
            
            if auto_sync:
                period.sync_to_game()
            
            logger.info(f"Incremented {team} goal in period {period_id}")
            return period

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error incrementing goal: {e}")
            return None

    def increment_period_foul(self, period_id: int, team: str, auto_sync: bool = True) -> Optional[Period]:
        """
        Increment foul for a team in a period
        
        Args:
            period_id: Period ID
            team: 'home' or 'away'
            auto_sync: Automatically sync to Game (default: True)
        
        Returns:
            Updated Period object or None if error
        """
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period with ID {period_id} not found")
            return None

        try:
            if team.lower() == 'home':
                period.increment_home_fouls()
            elif team.lower() == 'away':
                period.increment_away_fouls()
            else:
                raise ValueError(f"Invalid team: {team}. Must be 'home' or 'away'")
            
            db.session.commit()
            
            if auto_sync:
                period.sync_to_game()
            
            logger.info(f"Incremented {team} foul in period {period_id}")
            return period

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error incrementing foul: {e}")
            return None

    def sync_periods_to_game(self, game_id: int) -> bool:
        """
        Manually synchronize all periods to game
        
        This recalculates Game scores from Period data:
        - Goals = sum of all periods
        - Fouls = current active period
        
        Args:
            game_id: Game ID
        
        Returns:
            True if synced successfully, False otherwise
        """
        try:
            Period.sync_all_periods_to_game(game_id)
            logger.info(f"Synced all periods to game {game_id}")
            return True
        except Exception as e:
            logger.error(f"Error syncing periods to game: {e}")
            return False