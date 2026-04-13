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
from core.models.base_game        import BaseGame
from core.models.base_player      import BasePlayer
from core.models.base_team        import BaseTeam
from core.models.base_league      import BaseLeague
from core.models.base_period      import BasePeriod
from core.models.base_game_player import BaseGamePlayer
from core.models.base_game_timer  import BaseGameTimer
from core.models.base_settings    import BaseSettings

# Klasy konkretne — tabele które ZAWSZE są takie same we wszystkich modułach
from core.models.season           import Season
from core.models.stadium          import Stadium
from core.models.camera           import Camera
from core.models.commentator      import Commentator
from core.models.referee          import Referee
from core.models.event            import Event
from core.models.event_camera     import EventCamera
from core.models.game_event       import GameEvent
from core.models.game_camera      import GameCamera
from core.models.game_commentator import GameCommentator
from core.models.game_referee     import GameReferee
