"""Layout Manager — lista motywów overlayu i wybór aktywnego."""
import logging

from core.extensions import db

logger = logging.getLogger(__name__)


def _get_layout():
    from core.models.base_layout import get_layout_model
    return get_layout_model()


class LayoutManager:

    def get_all(self):
        Layout = _get_layout()
        return Layout.query.order_by(Layout.name).all()

    def get_active(self):
        Layout = _get_layout()
        return Layout.query.filter_by(is_active=True).first()

    def get_by_id(self, layout_id):
        Layout = _get_layout()
        return Layout.query.get(layout_id)

    def select(self, layout_id):
        """Ustawia is_active=True na wskazanym rekordzie i False na
        wszystkich innych — co najwyżej jeden aktywny naraz. layout_id=None
        (wybór pustej pozycji) gasi wszystkie — powrót do mechanizmu
        podstawowego. Zwraca wybrany Layout albo None."""
        Layout = _get_layout()
        rows = Layout.query.all()
        selected = None
        for row in rows:
            should_be_active = layout_id is not None and str(row.id) == str(layout_id)
            row.is_active = should_be_active
            if should_be_active:
                selected = row
        db.session.commit()
        return selected
