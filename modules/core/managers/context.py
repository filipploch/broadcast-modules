"""Kontekst transmisji w poleceniach do pluginów i w ich odpowiedziach (etap E2c, zasada 5 z koncepcji).

Kontekst to {'module', 'session_id', 'game_id', 'period_id'}. Moduł dokleja go do każdego polecenia do pluginu, plugin odsyła go
w odpowiedziach i zdarzeniach, a filtr odrzuca komunikaty ze starej sesji, starego meczu albo z innego modułu.

Reguły filtru (ContextFilter.check):
  - komunikat bez kontekstu przechodzi (zdarzenia samorzutne, starsze wersje pluginów);
  - porównywane są tylko identyfikatory obecne (nie None) w komunikacie: None znaczy "polecenie nie dotyczyło sesji/meczu";
  - niezgodny moduł, sesja albo mecz oznacza odrzucenie, z wyjątkiem kontekstów "zamykanych": przy zmianie meczu moduł wysyła
    jeszcze polecenia dotyczące starego meczu (np. pauza zegara) i na krótko dopuszcza odpowiedzi z jego kontekstu;
  - okres NIE służy do odrzucania: późny komunikat o poprzednim okresie tego samego meczu ma trafić do swojego okresu.
"""
import time
import threading

CLOSING_TTL_SECONDS = 15.0


def current_context(module_name=None, period_id=None):
    """Kontekst bieżącej transmisji wyliczony z bazy (nic nie jest trzymane w pamięci, więc przeżywa restart modułu)."""
    from core.managers import session_manager
    session_id = session_manager.current_session_id()
    game_id = session_manager.current_game_id() if session_id else None
    if period_id is None and game_id:
        period_id = session_manager.current_period_id()
    return {'module': module_name, 'session_id': session_id, 'game_id': game_id, 'period_id': period_id}


class ContextFilter:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._closing = []          # [(session_id, game_id, wygasa)]
        self._lock = threading.Lock()
        self.rejected = 0

    def allow_closing(self, context, ttl=CLOSING_TTL_SECONDS):
        """Dopuszcza na ttl sekund odpowiedzi z kontekstu meczu, który właśnie przestaje być bieżący."""
        if not context or context.get('game_id') is None:
            return
        with self._lock:
            self._closing.append((context.get('session_id'), context.get('game_id'), self._clock() + ttl))

    def _is_closing(self, session_id, game_id):
        now = self._clock()
        with self._lock:
            self._closing = [c for c in self._closing if c[2] > now]
            return any(s == session_id and g == game_id for s, g, _ in self._closing)

    def check(self, received, expected):
        """Zwraca (True, None) albo (False, powód) z listą niezgodnych identyfikatorów (oczekiwany i otrzymany)."""
        if not received:
            return True, None
        problems = []
        for key in ('module', 'session_id', 'game_id'):
            got = received.get(key)
            want = expected.get(key)
            if got is not None and got != want:
                problems.append(f"{key}: oczekiwano {want!r}, otrzymano {got!r}")
        if not problems:
            return True, None
        if all(not p.startswith('module') for p in problems) and received.get('module') in (None, expected.get('module')) \
                and self._is_closing(received.get('session_id'), received.get('game_id')):
            return True, None
        return False, '; '.join(problems)
