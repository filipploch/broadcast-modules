from core.managers.period_manager import PeriodManager as _CorePM
from core.extensions import db
import logging

logger = logging.getLogger(__name__)

HALF_DURATION_MS = 40 * 60 * 1000  # 40 minutes per half


class PeriodManager(_CorePM):
    def create_default_periods(self, game_id: int):
        """Garbarnia: 2 × 40 min, pause_at_limit=False (timer continues past limit)."""
        periods = []
        for order, desc in [(1, '1. połowa'), (2, '2. połowa')]:
            p = self.create_period(
                game_id=game_id,
                period_order=order,
                description=desc,
                limit=HALF_DURATION_MS,
                pause_at_limit=False,
            )
            p.update_timer_name()
            db.session.commit()
            periods.append(p)
        logger.info(f'Created default 2 periods (pause_at_limit=False) for game {game_id}')
        return periods

    def update_period_red_cards(self, period_id: int, home_red_cards: int, away_red_cards: int,
                                auto_sync: bool = True):
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period {period_id} not found")
            return None
        try:
            period.update_red_cards(home_red_cards, away_red_cards)
            db.session.commit()
            if auto_sync:
                period.sync_to_game()
            return period
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating red cards: {e}")
            return None

    def increment_period_red_card(self, period_id: int, team: str, value: int = 1,
                                  auto_sync: bool = True):
        period = self.get_period_by_id(period_id)
        if not period:
            logger.warning(f"Period {period_id} not found")
            return None
        try:
            if team.lower() == 'home':
                period.increment_home_red_cards(value)
            elif team.lower() == 'away':
                period.increment_away_red_cards(value)
            else:
                raise ValueError(f"Invalid team: {team}")
            db.session.commit()
            if auto_sync:
                period.sync_to_game()
            return period
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error incrementing red card: {e}")
            return None
