"""BaseSettingsMixin — abstrakcyjna klasa bazowa dla ustawień aplikacji.

Singleton (zawsze jeden wiersz, id=1). Od etapu E1 zawiera wyłącznie ustawienia aplikacji niezwiązane
z aktualnym meczem: sezon wybrany do przeglądania list (browse_season_id), timery (do końca E1),
odwrócenie tablicy wyników, ścieżka nagrania OBS (w E2 przechodzi do stanu sesji).

Aktualny mecz, okres, sezon meczu i seria rzutów karnych NIE są tu przechowywane: wynikają z aktywnego meczu
otwartej sesji transmisji (core/managers/session_manager.py). Właściwości current_* poniżej to tylko
warstwa zgodności (odczyt) dla plików specific_* w modułach; zostaną usunięte przy scalaniu modułów w E2.
"""
from core.extensions import db
from datetime import datetime
import json


class BaseSettingsMixin:

    id                     = db.Column(db.Integer, primary_key=True)

    # Sezon wybrany do przeglądania list w interfejsie. Ustawienie interfejsu, bez związku z transmisją:
    # nie zmienia się przy wyborze meczu ani przy tworzeniu sezonu.
    @db.declared_attr
    def browse_season_id(cls):
        return db.Column(db.Integer, db.ForeignKey('seasons.id'), nullable=True)

    current_timers         = db.Column(db.Text,    nullable=True)
    is_scoreboard_reversed = db.Column(db.Boolean, default=False)
    obs_record_filepath    = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Settings browse_season_id={self.browse_season_id}>'

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

    # ── Sezon przeglądania list (ustawienie interfejsu) ──────────────────────
    @classmethod
    def set_browse_season(cls, season_id):
        s = cls.get_settings()
        s.browse_season_id = season_id
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

    # ── Warstwa zgodności (tylko odczyt) — usunąć w E2 ────────────────────────
    # Aktualny mecz/okres/seria karnych to stan sesji transmisji, nie ustawienia aplikacji.
    @property
    def current_game_id(self):
        from core.managers import session_manager
        return session_manager.current_game_id()

    @property
    def current_game(self):
        from core.managers import session_manager
        return session_manager.current_game()

    @property
    def current_period_id(self):
        from core.managers import session_manager
        return session_manager.current_period_id()

    @property
    def current_period(self):
        from core.managers import session_manager
        return session_manager.current_period()

    @property
    def current_shootout(self):
        from core.managers import session_manager
        return session_manager.current_shootout()

    @property
    def current_shootout_id(self):
        so = self.current_shootout
        return so.id if so is not None else None

    @property
    def current_season_id(self):
        """Sezon do przeglądania list (NIE sezon transmitowanego meczu; ten daje session_manager.current_season_id()).

        Kolejność: sezon wybrany w interfejsie (browse_season_id) → sezon transmitowanego meczu → najnowszy sezon z meczami
        → najnowszy sezon. Dzięki temu nowo utworzony, pusty sezon nie zmienia domyślnego widoku list.
        """
        if self.browse_season_id:
            return self.browse_season_id
        from core.managers import session_manager
        sid = session_manager.current_season_id()
        if sid:
            return sid
        from core.models.base_season import get_season_model
        Season = get_season_model()
        seasons = Season.query.order_by(Season.number.desc()).all()
        for season in seasons:
            if season.total_games > 0:
                return season.id
        return seasons[0].id if seasons else None

    @property
    def current_season(self):
        from core.models.base_season import get_season_model
        sid = self.current_season_id
        return get_season_model().query.get(sid) if sid else None

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