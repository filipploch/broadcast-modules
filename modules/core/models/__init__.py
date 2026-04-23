"""Core models — wspólne dla wszystkich modułów.

Klasy abstrakcyjne (__abstract__ = True, nie tworzą tabel):
  BaseGame, BasePlayer, BaseTeam, BaseLeague,
  BasePeriod, BaseGamePlayer, BaseGameTimer, BaseSettings

Klasy konkretne ZAWSZE wspólne (żaden moduł ich nie nadpisuje):
  Season, Stadium, Camera, Commentator, Referee,
  Event, EventCamera, GameEvent, GameCamera, GameCommentator, GameReferee

NIE eksportujemy stąd: Settings, Period, GamePlayer, GameTimer
  — moduł definiuje własne wersje tych tabel (dziedzicząc z Base*)
  — lub importuje wersję core bezpośrednio jeśli nie potrzebuje rozszerzeń:
      from core.models.period import Period
"""
# Klasy abstrakcyjne — bezpieczne do importowania zawsze
from core.models.base_game        import BaseGameMixin
from core.models.base_player      import BasePlayerMixin
from core.models.base_team        import BaseTeamMixin
from core.models.base_league      import BaseLeagueMixin
from core.models.base_period      import BasePeriodMixin
from core.models.base_game_player import BaseGamePlayerMixin
from core.models.base_game_timer  import BaseGameTimerMixin
from core.models.base_settings    import BaseSettingsMixin

# Klasy konkretne — tabele które ZAWSZE są takie same we wszystkich modułach
from core.models.base_season           import BaseSeasonMixin
from core.models.base_stadium          import BaseStadiumMixin
from core.models.base_camera           import BaseCameraMixin
from core.models.base_commentator      import BaseCommentatorMixin
from core.models.base_referee          import BaseRefereeMixin
from core.models.base_event            import BaseEventMixin
from core.models.base_event_camera     import BaseEventCameraMixin
from core.models.base_game_event       import BaseGameEventMixin
from core.models.base_game_camera      import BaseGameCameraMixin
from core.models.base_game_commentator import BaseGameCommentatorMixin
from core.models.base_game_referee     import BaseGameRefereeMixin
