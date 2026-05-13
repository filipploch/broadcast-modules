from core.managers.period_manager import PeriodManager as _CorePM
from core.extensions import db
import logging

logger = logging.getLogger(__name__)

class PeriodManager(_CorePM):
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
