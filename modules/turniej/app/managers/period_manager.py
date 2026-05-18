from core.managers.period_manager import PeriodManager as _CorePM
from core.extensions import db
import logging

logger = logging.getLogger(__name__)



class PeriodManager(_CorePM):
    def create_default_periods(self, game_id: int):
        """Turniej: 1 okres 15 minut, timer liczony w górę (pause_at_limit=False)."""
        period = self.create_period(
            game_id=game_id,
            period_order=1,
            description="Mecz",
            limit=900000,
            pause_at_limit=False,
        )
        period.update_timer_name()
        db.session.commit()
        logger.info(f"Created 1 period (15 min, count-up) for game {game_id}")
        return [period]

    def update_period_fouls(self, period_id: int, home_fouls: int, away_fouls: int,
                           auto_sync: bool = True):
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

    def increment_period_foul(self, period_id: int, team: str, value: int = 1, auto_sync: bool = True):
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period with ID {period_id} not found")
            return None

        try:
            if team.lower() == 'home':
                period.increment_home_fouls(value)
            elif team.lower() == 'away':
                period.increment_away_fouls(value)
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
