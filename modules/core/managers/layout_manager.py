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

    def create(self, name):
        """Rejestruje nowy motyw w bazie (is_active=False). Jeśli rekord
        o tej nazwie już istnieje, zwraca go bez zmian — idempotentne,
        bo może być wywołane zarówno dla folderu już istniejącego na dysku
        (register_layout) jak i dla nowo utworzonego przez huba
        (create_layout)."""
        Layout = _get_layout()
        existing = Layout.query.filter_by(name=name).first()
        if existing:
            return existing
        layout = Layout(name=name, is_active=False)
        db.session.add(layout)
        db.session.commit()
        return layout

    def list_unregistered_style_folders(self, style_dir):
        """Porównuje podfoldery fizycznie obecne w style_dir (Path) z
        nazwami motywów już zapisanymi w bazie. Zwraca listę nazw folderów
        bez odpowiadającego rekordu. Odporne na brak/niedostępność
        style_dir — w takim wypadku zwraca []."""
        try:
            if not style_dir.is_dir():
                return []
            disk_names = sorted(p.name for p in style_dir.iterdir() if p.is_dir())
        except OSError:
            logger.warning("Nie udało się zeskanować %s", style_dir, exc_info=True)
            return []
        known_names = {row.name for row in self.get_all()}
        return [name for name in disk_names if name not in known_names]

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
