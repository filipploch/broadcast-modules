"""Period Manager - handles CRUD operations for Period model"""
from typing import List, Optional
from core.extensions import db
import logging

def _get_game():
    from core.models.base_game import get_game_model
    return get_game_model()


def _get_period():
    from core.models.base_period import get_period_model
    return get_period_model()


logger = logging.getLogger(__name__)


class PeriodManager:
    """Manager for Period CRUD operations"""

    def create_period(self, game_id: int, period_order: int, description: str,
                     limit: int = 1200000, pause_at_limit: bool = True,
                     auto_calculate_initial_time: bool = True):
        """
        Create new period for a game

        Args:
            game_id: Game ID
            period_order: Period order (1, 2, 3, etc.)
            description: Period description (e.g., "1. połowa", "2. połowa")
            limit: Time limit in milliseconds (default: 1200000 = 20 minutes)
            pause_at_limit: Whether to pause at time limit (default: True)
            auto_calculate_initial_time: Auto-calculate initial_time from previous periods (default: True)

        Returns:
            Period object or None if error

        Raises:
            ValueError if game not found or period_order already exists
        """
        # Validate game exists
        game = _get_game().query.get(game_id)
        if not game:
            raise ValueError(f"Mecz o ID {game_id} nie istnieje")

        # Check if period_order already exists for this game
        existing = _get_period().query.filter_by(game_id=game_id, period_order=period_order).first()
        if existing:
            raise ValueError(f"Część {period_order} już istnieje dla tego meczu")

        try:
            # initial_time = suma limitów wszystkich poprzednich części
            # limit        = czas trwania tej części (timer-plugin liczy od 0)
            if auto_calculate_initial_time:
                PeriodCls = _get_period()
                initial_time = PeriodCls.calculate_initial_time_for_period(
                PeriodCls, game_id, period_order)
            else:
                initial_time = 0

            period = _get_period()(
                game_id=game_id,
                period_order=period_order,
                description=description,
                initial_time=initial_time,
                limit=limit,          # czas trwania tej części, NIE suma kumulatywna
                pause_at_limit=pause_at_limit,
                status=_get_period().STATUS_NOT_STARTED
            )
            db.session.add(period)
            db.session.commit()

            logger.info(f"Created period {period_order} for game {game_id}: {description}")
            return period

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating period: {e}")
            raise

    def create_default_periods(self, game_id: int):
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
            limit=1200000,  # 20 minutes
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
            limit=1200000,  # 20 minutes
            pause_at_limit=True
        )
        period2.update_timer_name()
        db.session.commit()
        periods.append(period2)
        
        logger.info(f"Created default 2 periods for game {game_id}")
        return periods

    def get_periods_by_game(self, game_id: int):
        """Get all periods for a game, ordered by period_order"""
        Period = _get_period()
        return _get_period().query.filter_by(game_id=game_id).order_by(Period.period_order).all()

    def get_period_by_id(self, period_id: int):
        """Get period by ID"""
        return _get_period().query.get(period_id)

    def update_period(self, period_id: int, description: str = None, 
                     limit: int = None, pause_at_limit: bool = None,
                     status: int = None):
        """
        Update period

        Args:
            period_id: Period ID
            description: New description (optional)
            limit: New time limit in milliseconds (optional)
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
            if limit is not None:
                period.limit = limit
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

    def set_period_status(self, period_id: int, status: int):
        """
        Set period status
        
        Args:
            period_id: Period ID
            status: New status (0=not started, 1=live, 2=finished)
        
        Returns:
            Updated Period object or None if error
        """
        return self.update_period(period_id, status=status)

    def start_period(self, period_id: int):
        """
        Start a period (set status to PENDING) and setup timers
        
        This method:
        1. Sets period status to PENDING
        2. Creates/updates main timer in Settings (state: idle, NOT started)
        3. Restores penalty timers if they exist (for periods > 1)
        4. Removes penalty timers with limit_reached status
        """
        from core.models.base_settings import get_settings_model
        Settings = get_settings_model()
        from core.managers import get_timer_manager
        
        period = self.set_period_status(period_id, _get_period().STATUS_PENDING)
        if not period:
            return None
        
        timer_manager = get_timer_manager()
        
        # Prepare main timer data
        main_timer_data = {
            "timer_id": period.main_timer_name,
            "timer_type": "independent",
            "initial_time": period.initial_time,
            "limit": period.limit,
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
            _remaining_penalties = current_timers.get("penalties", {"home": [], "away": []})
            remaining_penalties = _remaining_penalties['home'] + _remaining_penalties['away']
            
            # Create main timer
            timer_manager.create_timer(
                timer_id=period.main_timer_name,
                timer_type="independent",
                initial_time=period.initial_time,
                limit=period.limit,
                pause_at_limit=period.pause_at_limit,
                metadata={
                    "description": period.description,
                    "period": period.period_order,
                    "timer_class": "main"
                }
            )
            
            # Update main timer in Settings
            Settings.update_main_timer(main_timer_data)
            
            # Recreate penalty timers as dependent on new period's main timer.
            # elapsed_time from previous period becomes the new initial_time (UI offset),
            # and the remaining time = original limit - elapsed becomes the new limit
            # (plugin counts from 0, so it only needs to run for the remainder).
            for penalty in remaining_penalties:
                penalty_elapsed = penalty.get("elapsed_time", 0) or 0
                penalty_limit   = penalty.get("limit", 120000) or 120000
                remaining_limit = max(penalty_limit - penalty_elapsed, 0)

                if remaining_limit == 0:
                    # Penalty already fully served — skip
                    continue

                penalty_metadata = penalty.get("metadata", {})
                timer_manager.create_timer(
                    timer_id=penalty.get("timer_id"),
                    timer_type="dependent",
                    parent_id=period.main_timer_name,
                    initial_time=penalty_elapsed,   # UI shows time already served
                    limit=remaining_limit,          # plugin runs only for the remainder
                    pause_at_limit=True,
                    metadata=penalty_metadata
                )
        else:
            # First period - just create main timer
            timer_manager.create_timer(
                timer_id=period.main_timer_name,
                timer_type="independent",
                initial_time=period.initial_time,
                limit=period.limit,
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

    def finish_period(self, period_id: int):
        """
        Finish a period (set status to FINISHED)
        
        This method:
        1. Stops all running timers
        2. Updates timer states in Settings with current elapsed times
        3. Sets period status to FINISHED
        """
        from core.models.base_settings import get_settings_model
        Settings = get_settings_model()
        from core.managers import get_timer_manager
        
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
                main_timer["elapsed_time"] = timer_state.get("elapsed_time", main_timer.get("elapsed_time", 0))
                Settings.update_main_timer(main_timer)
        
        # Stop and update all penalty timers
        _penalties = current_timers.get("penalties", {"home": [], "away": []})
        penalties = _penalties['home'] + _penalties['away']
        for i, penalty in enumerate(penalties):
            timer_id = penalty.get("timer_id")
            if timer_id:
                timer_state = timer_manager.get_timer_state(timer_id)
                if timer_state and timer_state.get("state") == "running":
                    timer_manager.pause_timer(timer_id)
                
                # Update penalty timer with current state
                if timer_state:
                    penalty["state"] = timer_state.get("state", "paused")
                    penalty["elapsed_time"] = timer_state.get("elapsed_time", penalty.get("elapsed_time", 0))
                    Settings.update_penalty_timer(timer_id, penalty)
        
        # Set period status to FINISHED
        return self.set_period_status(period_id, _get_period().STATUS_FINISHED)

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
        
    #   ORYGINAŁ:
    # def get_current_period(self, game_id: int):
    #     """Get currently active period for a game"""
    #     return _get_period().query.filter_by(
    #         game_id=game_id,
    #         status=_get_period().STATUS_PENDING
    #     ).first()

    def get_current_period(self, game_id: int):
        """Get currently active period for a game"""
        return _get_period().query.filter_by(game_id=game_id, status=_get_period().STATUS_PENDING).first()
    
    def get_all_game_periods(self, game_id: int):
        """Get currently active period for a game"""
        return _get_period().query.filter_by(
            game_id=game_id
        ).all()

    def update_period_score(self, period_id: int, home_goals: int, away_goals: int,
                           auto_sync: bool = True):
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

    # def update_period_fouls(self, period_id: int, home_fouls: int, away_fouls: int,
    #                        auto_sync: bool = True):
    #     """
    #     Update period fouls
        
    #     Args:
    #         period_id: Period ID
    #         home_fouls: Home team fouls in this period
    #         away_fouls: Away team fouls in this period
    #         auto_sync: Automatically sync to Game (default: True)
        
    #     Returns:
    #         Updated Period object or None if error
    #     """
    #     period = self.get_period_by_id(period_id)
    #     if not period:
    #         logger.warning(f"Period with ID {period_id} not found")
    #         return None

    #     try:
    #         period.update_fouls(home_fouls, away_fouls)
    #         db.session.commit()
            
    #         if auto_sync:
    #             period.sync_to_game()
            
    #         logger.info(f"Updated period {period_id} fouls: {home_fouls}:{away_fouls}")
    #         return period

    #     except Exception as e:
    #         db.session.rollback()
    #         logger.error(f"Error updating period fouls: {e}")
    #         return None

    def increment_period_goal(self, period_id: int, team: str, value: int = 1, auto_sync: bool = True):
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
                period.increment_home_goals(value)
            elif team.lower() == 'away':
                period.increment_away_goals(value)
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

    # def increment_period_foul(self, period_id: int, team: str, value: int = 1, auto_sync: bool = True):
    #     """
    #     Increment foul for a team in a period
        
    #     Args:
    #         period_id: Period ID
    #         team: 'home' or 'away'
    #         auto_sync: Automatically sync to Game (default: True)
        
    #     Returns:
    #         Updated Period object or None if error
    #     """
    #     period = self.get_period_by_id(period_id)
    #     if not period:
    #         logger.warning(f"Period with ID {period_id} not found")
    #         return None

    #     try:
    #         if team.lower() == 'home':
    #             period.increment_home_fouls(value)
    #         elif team.lower() == 'away':
    #             period.increment_away_fouls(value)
    #         else:
    #             raise ValueError(f"Invalid team: {team}. Must be 'home' or 'away'")
            
    #         db.session.commit()
            
    #         if auto_sync:
    #             period.sync_to_game()
            
    #         logger.info(f"Incremented {team} foul in period {period_id}")
    #         return period

    #     except Exception as e:
    #         db.session.rollback()
    #         logger.error(f"Error incrementing foul: {e}")
    #         return None

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
            Period = _get_period()
            Period.sync_all_periods_to_game(game_id)
            logger.info(f"Synced all periods to game {game_id}")
            return True
        except Exception as e:
            logger.error(f"Error syncing periods to game: {e}")
            return False