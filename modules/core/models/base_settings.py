"""BaseSettingsMixin — abstrakcyjna klasa bazowa dla ustawień aplikacji.

Singleton (zawsze jeden wiersz, id=1). Zawiera wspólne pola
dla wszystkich modułów: bieżący sezon, mecz, okres, timery,
odwrócenie tablicy wyników, ścieżka nagrania OBS.

Moduł może rozszerzyć tę klasę o własne pola
(np. current_shootout_id w futsalu).
"""
from core.extensions import db
from datetime import datetime
import json


class BaseSettingsMixin:

    id                     = db.Column(db.Integer, primary_key=True)
    @db.declared_attr
    def current_season_id(cls):
        return db.Column(db.Integer, db.ForeignKey('seasons.id'), nullable=True)

    @db.declared_attr
    def current_game_id(cls):
        return db.Column(db.Integer, db.ForeignKey('games.id'), nullable=True)

    @db.declared_attr
    def current_period_id(cls):
        return db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=True)
    current_timers         = db.Column(db.Text,    nullable=True)
    is_scoreboard_reversed = db.Column(db.Boolean, default=False)
    obs_record_filepath    = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def __repr__(self):
        # Relacje (current_season, current_game etc.) definiowane w klasie modułu
        return (f'<Settings season_id={self.current_season_id} '
                f'game_id={self.current_game_id} '
                f'period_id={self.current_period_id}>')

    # ── Singleton ─────────────────────────────────────────────────────────────
    @classmethod
    def get_settings(cls):
        """Get or create singleton settings instance.
        
        UWAGA: Tę metodę wywołuj tylko na konkretnej klasie (np. app.models.Settings),
        nie na BaseSettingsMixin. BaseSettingsMixin jest abstrakcyjna i nie ma tabeli.
        """
        settings = cls.query.first()
        if not settings:
            settings = cls()
            db.session.add(settings)
            db.session.commit()
        return settings

    # ── BaseSeasonMixin / Game / Period ─────────────────────────────────────────────────
    @classmethod
    def set_current_season(cls, season_id):
        s = cls.get_settings()
        s.current_season_id = season_id
        s.updated_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def set_current_game(cls, game_id):
        s = cls.get_settings()
        s.current_game_id = game_id
        s.updated_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def set_current_period(cls, period_id):
        s = cls.get_settings()
        s.current_period_id = period_id
        s.updated_at = datetime.utcnow()
        db.session.commit()

    # ── Scoreboard ────────────────────────────────────────────────────────────
    @classmethod
    def set_scoreboard_order(cls, is_reversed):
        s = cls.get_settings()
        s.is_scoreboard_reversed = is_reversed
        s.updated_at = datetime.utcnow()
        db.session.commit()

    # ── OBS ───────────────────────────────────────────────────────────────────
    @classmethod
    def set_obs_record_filepath(cls, filepath):
        s = cls.get_settings()
        s.obs_record_filepath = filepath
        s.updated_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def get_obs_record_filepath(cls):
        return cls.get_settings().obs_record_filepath

    # ── Timery ────────────────────────────────────────────────────────────────
    @classmethod
    def get_current_timers(cls):
        s = cls.get_settings()
        if not s.current_timers:
            return {'main': None, 'penalties': {'home': [], 'away': []}}
        try:
            return json.loads(s.current_timers)
        except (json.JSONDecodeError, TypeError):
            return {'main': None, 'penalties': {'home': [], 'away': []}}

    @classmethod
    def set_current_timers(cls, timers_data):
        s = cls.get_settings()
        s.current_timers = json.dumps(timers_data)
        s.updated_at = datetime.utcnow()
        db.session.commit()

    @classmethod
    def update_main_timer(cls, timer_data):
        timers = cls.get_current_timers()
        timers['main'] = timer_data
        cls.set_current_timers(timers)

    @classmethod
    def add_penalty_timer(cls, team, timer_data):
        timers = cls.get_current_timers()
        timers.setdefault('penalties', {'home': [], 'away': []})
        timers['penalties'][team].append(timer_data)
        cls.set_current_timers(timers)

    @classmethod
    def update_penalty_timer(cls, timer_id, timer_data):
        timers = cls.get_current_timers()
        for side in ('home', 'away'):
            for i, p in enumerate(timers.get('penalties', {}).get(side, [])):
                if p.get('timer_id') == timer_id:
                    timers['penalties'][side][i] = timer_data
                    break
        cls.set_current_timers(timers)

    @classmethod
    def remove_limit_reached_penalties(cls):
        timers = cls.get_current_timers()
        for side in ('home', 'away'):
            timers['penalties'][side] = [
                p for p in timers['penalties'].get(side, [])
                if p.get('state') != 'limit_reached'
            ]
        cls.set_current_timers(timers)

    @classmethod
    def clear_timers(cls):
        cls.set_current_timers({'main': None, 'penalties': {'home': [], 'away': []}})

    @classmethod
    def validate_period_for_game(cls):
        s = cls.get_settings()
        if s.current_period_id is None:
            return True
        if s.current_game_id is None:
            return False
        from core.models.base_period import get_period_model
        Period = get_period_model()
        period = Period.query.get(s.current_period_id)
        if not period:
            return False
        return period.game_id == s.current_game_id

def get_settings_model():
    """Zwraca konkretną klasę BaseLeagueMixin zarejestrowaną przez aktywny moduł."""
    from core.extensions import db
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if (getattr(cls, '__tablename__', None) == 'settings'
                and issubclass(cls, BaseSettingsMixin)):
            return cls
    raise RuntimeError(
        "Nie znaleziono klasy BaseSettingsMixin w rejestrze SQLAlchemy. "
        "Upewnij się że model jest zaimportowany przed wywołaniem get_settings_model()."
    )