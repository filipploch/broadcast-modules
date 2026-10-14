"""Straż zdarzeń panelu (E2d1): polecenia zegara i zapisy zdarzeń meczu są przyjmowane tylko przy otwartej sesji transmisji
i aktywnym meczu. Polecenie z innego meczu niż aktywny (np. kliknięcie w starej karcie przeglądarki, przechowane przez klienta
socket.io w czasie rozłączenia i wysłane po ponownym połączeniu) jest odrzucane z wpisem w logu i komunikatem 'error'.

Straż owija obsługę już zarejestrowanych zdarzeń (socketio.server.handlers), więc nie zmienia ich kodu. Wołać po
zarejestrowaniu wszystkich zdarzeń (core i moduł)."""
import functools
import logging

logger = logging.getLogger(__name__)

# Zdarzenia zmieniające zegar, wynik albo dodające zdarzenie meczu. Nie są pilnowane: zdarzenia tylko odczytujące
# (timers_get_all, timer_get_state, ...), edycja zdarzenia po jego numerze (update/hide/restore_game_event: jednoznaczna)
# i tworzenie zegarów rafting/slalom. Uwaga: start/pauza takiego zegara idzie przez timer_start/timer_pause, więc bez sesji
# też zostanie odrzucony; moduły NALF i Garbarnia ich nie używają (dyscypliny z zegarem poza meczem: E9).
GUARDED_EVENTS = (
    'timer_start', 'timer_pause', 'timer_resume', 'timer_reset', 'timer_adjust', 'timer_set_time',
    'timer_create', 'match_timer_create', 'penalty_timer_create',
    'timer_plugin_create_timer', 'timer_plugin_set_elapsed_time', 'timer_plugin_start_timer',
    'change_game_value', 'broadcast_goal', 'add_game_event_to_db',
)


def refusal_reason(event, data):
    """Powód odrzucenia polecenia albo None, gdy można je przyjąć. Wymaga kontekstu aplikacji."""
    from core.managers import session_manager
    if session_manager.get_open_session() is None:
        return 'brak otwartej sesji transmisji'
    game_id = session_manager.current_game_id()
    if game_id is None:
        return 'sesja nie ma aktywnego meczu'
    timer_id = data.get('timer_id') if isinstance(data, dict) else None
    if timer_id:
        # Zegar główny okresu innego meczu niż aktywny: polecenie nie dotyczy transmitowanego meczu
        from core.models.base_period import get_period_model
        period = get_period_model().query.filter_by(main_timer_name=timer_id).first()
        if period is not None and period.game_id != game_id:
            return f'zegar {timer_id} należy do innego meczu (id {period.game_id}) niż aktywny (id {game_id})'
    return None


def guard_events(app, socketio, events=GUARDED_EVENTS):
    """Owija obsługę wskazanych zdarzeń kontrolą sesji i meczu. Zwraca listę faktycznie owiniętych zdarzeń."""
    handlers = socketio.server.handlers.get('/', {})
    wrapped = []
    for name in events:
        handler = handlers.get(name)
        if handler is None or getattr(handler, '_bm_guarded', False):
            continue
        handlers[name] = _wrap(app, socketio, name, handler)
        wrapped.append(name)
    return wrapped


def _wrap(app, socketio, name, handler):
    @functools.wraps(handler)
    def guarded(sid, *args, **kwargs):
        data = args[0] if args else None
        try:
            with app.app_context():
                reason = refusal_reason(name, data)
        except Exception:
            logger.exception('Straż zdarzeń: nie udało się sprawdzić sesji dla %s; zdarzenie przepuszczone', name)
            reason = None
        if reason:
            logger.warning('Odrzucono zdarzenie %s: %s', name, reason)
            # Rozgłoszenie jak w pozostałych komunikatach 'error' modułu: panel to kilka ramek (lewa, środkowa, prawa), każda z własnym
            # połączeniem, a komunikat pokazuje ta z obsługą 'error' (ui-jinja.js), więc wysłanie tylko do nadawcy zwykle nic by nie pokazało.
            socketio.emit('error', {'message': f'Polecenie nie zostało wykonane ({name}): {reason}'})
            return None
        return handler(sid, *args, **kwargs)
    guarded._bm_guarded = True
    return guarded
