"""Komunikaty usług uruchamianych przez HUB (OBS, moduł) dla paska w panelu (E2d2).

HUB wysyła modułowi `service_status` (kind: error, recovered, restarted, gave_up, info). Moduł trzyma aktualne komunikaty
(po jednym na klucz) i przy każdej zmianie rozsyła pełną listę do paneli ('service_notices'); panel pyta o listę po połączeniu
('get_service_notices'), więc komunikat przeżywa odświeżenie strony. Komunikat znika, gdy problem mija albo operator go zamknie.

Po automatycznym restarcie OBS (przy otwartej sesji) komunikat "OBS uruchomiony ponownie — wznów stream i nagrywanie"
zostaje, dopóki obs-ws-plugin nie zgłosi, że stream działa, albo operator go nie zamknie."""
import threading

from flask import current_app

OBS_RESTARTED_KEY = 'obs-restarted'
OBS_RESTARTED_TEXT = 'OBS uruchomiony ponownie — wznów stream i nagrywanie'

LABELS = {'obs': 'OBS', 'module': 'Moduł'}


class ServiceNotices:
    def __init__(self):
        self.lock = threading.Lock()
        self.notices = {}   # klucz -> {'key', 'text', 'level'}

    # -- zmiany
    def set(self, key, text, level='error'):
        with self.lock:
            if self.notices.get(key, {}).get('text') == text:
                return
            self.notices[key] = {'key': key, 'text': text, 'level': level}
        self._emit()

    def clear(self, *keys):
        with self.lock:
            changed = False
            for key in keys:
                changed = self.notices.pop(key, None) is not None or changed
        if changed:
            self._emit()

    def snapshot(self):
        with self.lock:
            return list(self.notices.values())

    def on_service_event(self, service_id, kind, message):
        """Przekłada zdarzenie usługi z HUB-a na komunikat w panelu."""
        label = LABELS.get(service_id, service_id)
        message = message or ''
        problem_keys = (f'{service_id}-error', f'{service_id}-gave-up')
        if kind == 'error':
            self.set(f'{service_id}-error', f'{label}: {message}', 'error')
        elif kind == 'gave_up':
            self.set(f'{service_id}-gave-up', message or f'{label}: limit automatycznych restartów wyczerpany', 'error')
        elif kind == 'restarted':
            self.clear(*problem_keys)
            if service_id == 'obs':
                self.set(OBS_RESTARTED_KEY, OBS_RESTARTED_TEXT, 'warning')
            else:
                self.set(f'{service_id}-restarted', f'{label} uruchomiony ponownie', 'warning')
        elif kind == 'recovered':
            self.clear(*problem_keys)
        elif kind == 'info':
            self.set(f'{service_id}-info', f'{label}: {message}', 'info')
        else:
            current_app.logger.warning(f'service_status: nieznany rodzaj zdarzenia {kind!r} usługi {service_id}')

    def on_obs_stream_running(self):
        """obs-ws-plugin zgłosił, że stream działa: zdejmuje przypomnienie o wznowieniu streamu po restarcie OBS."""
        self.clear(OBS_RESTARTED_KEY)

    def _emit(self):
        try:
            from core.extensions import socketio
            socketio.emit('service_notices', self.snapshot())
        except Exception as e:
            current_app.logger.error(f'Nie udało się wysłać komunikatów usług do panelu: {e}')
