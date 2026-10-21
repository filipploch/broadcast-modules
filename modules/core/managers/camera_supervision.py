"""Nadzór nad kamerami recorder-pluginu (E2d3b, krok 3): które kamery mają działać, stan każdej z nich, paski w panelu,
źródła sCameraN w OBS.

Zasady (wariant B):
- Lista kamer, które mają działać = kamery przypisane do bieżącego meczu (opcje meczu) + kamera 1 ZAWSZE (także bez sesji i meczu).
- Pełną listę wysyłamy pluginowi (`set_active_cameras`) po każdej rejestracji pluginu w HUB-ie i po każdej zmianie: opcje meczu,
  zmiana meczu w sesji, otwarcie i zamknięcie sesji. Ta sama lista wysłana dwa razy nic nie zmienia (plugin jest idempotentny),
  a moduł pomija powtórzenie, dopóki plugin się nie zarejestruje od nowa.
- Obraz z kamery nie zależy od nagrywania: plugin odbiera obraz i wystawia podgląd SRT dla OBS, gdy tylko kamera jest na liście.
- Usunięcie z listy kamery, która nagrywa, wymaga potwierdzenia operatora (`stop_recording_for_removed`); bez niego plugin
  odmawia i odpowiada listą `blocked`.
- Pasek „KAMERA N: …” tylko dla kamer z listy; trzy rozróżnione stany: brak obrazu / nagrywa wprost bez podglądu w OBS /
  przerwa w nagraniu.
- Po „kamera N działa” (camera_state: running) moduł ustawia URL SRT źródła sCameraN i odświeża je w OBS; odświeża je też po
  starcie podglądu SRT (stream_changed), bo nasłuch SRT powstaje chwilę po zgłoszeniu „działa”. Konfiguracji OBS nie zmieniamy.
"""
import threading

from flask import current_app

MAIN_CAMERA = 'camera1'

# Stany kamery zgłaszane przez plugin (feed.go)
STATE_OFF, STATE_STARTING, STATE_RUNNING, STATE_ERROR = 'off', 'starting', 'running', 'error'


def camera_number(camera_id):
    """'camera2' -> 2 (do tekstów w panelu)."""
    digits = ''.join(ch for ch in str(camera_id) if ch.isdigit())
    return digits or str(camera_id)


class CameraSupervision:
    """Mieszanka dla RecorderManager. Wymaga: self.hub_client, self.recorder_plugin_id, self.recorder_plugin_ip, self._emit_to_ui."""

    # ── stan ─────────────────────────────────────────────────────────────────

    def _sup(self):
        sup = self.__dict__.get('_camera_sup')
        if sup is None:
            sup = {'lock': threading.RLock(), 'cameras': {}, 'interrupted': {}, 'last_sent': None}
            self.__dict__['_camera_sup'] = sup
        return sup

    def camera_states(self):
        """Kopia stanu kamer wg ostatnich zgłoszeń pluginu: {camera_id: {state, wanted, recording, streaming, error, interrupted}}."""
        sup = self._sup()
        with sup['lock']:
            out = {}
            for cid, info in sup['cameras'].items():
                item = dict(info)
                item['interrupted'] = sup['interrupted'].get(cid)
                out[cid] = item
            return out

    def is_camera_recording(self, camera_id):
        sup = self._sup()
        with sup['lock']:
            return bool(sup['cameras'].get(camera_id, {}).get('recording'))

    # ── lista kamer, które mają działać ──────────────────────────────────────

    def wanted_cameras(self):
        """Kamery bieżącego meczu + kamera 1 zawsze. Bez sesji lub meczu: tylko kamera 1."""
        wanted = {MAIN_CAMERA}
        try:
            from core.managers import session_manager
            game_id = session_manager.current_game_id()
            if game_id:
                from core.managers.game_camera_manager import GameCameraManager
                wanted |= {gc.device_name for gc in GameCameraManager().get_cameras_for_game(game_id)}
        except Exception as e:
            current_app.logger.error(f'wanted_cameras: nie udało się odczytać kamer meczu (zostaje kamera 1): {e}')
        return sorted(wanted)

    def sync_cameras(self, stop_recording_for_removed=False, force=False):
        """Wysyła pluginowi pełną listę kamer. Zwraca True, gdy polecenie poszło. Powtórzenia tej samej listy są pomijane
        (chyba że force albo stop_recording_for_removed)."""
        if self.hub_client is None:
            return False
        wanted = self.wanted_cameras()
        sup = self._sup()
        with sup['lock']:
            if not force and not stop_recording_for_removed and sup['last_sent'] == wanted:
                return False
        ok = self.hub_client.send_to_plugin(self.recorder_plugin_id, 'set_active_cameras', {
            'cameras': wanted,
            'stop_recording_for_removed': bool(stop_recording_for_removed),
        })
        if ok:
            with sup['lock']:
                sup['last_sent'] = wanted
            current_app.logger.info(f'📷 Wysłano pluginowi listę kamer: {wanted}')
        return bool(ok)

    def on_recorder_registered(self):
        """Plugin zarejestrował się w HUB-ie (start, restart pluginu, restart Debiana lub HUB-a): pełna lista od nowa."""
        sup = self._sup()
        with sup['lock']:
            sup['last_sent'] = None
        self.sync_cameras(force=True)

    def on_recorder_disconnected(self):
        """Plugin rozłączony: stan kamer nieznany; pasek pluginu mówi o rozłączeniu, pasków kamer nie dublujemy."""
        sup = self._sup()
        with sup['lock']:
            sup['cameras'].clear()
            sup['interrupted'].clear()
            sup['last_sent'] = None
        self._refresh_camera_notices()
        self._emit_camera_states()

    # ── potwierdzenie usunięcia kamery, która nagrywa ────────────────────────

    def check_camera_assignment(self, game_id, data):
        """Sprawdza zapis kamer z opcji meczu PRZED zmianą w bazie. Zwraca None (można zapisywać) albo (kod_http, treść_odpowiedzi).

        - kamera 1 (wejście HDMI 1) musi zostać przypisana,
        - usunięcie kamery, która nagrywa (dotyczy bieżącego meczu), wymaga `confirm_stop_recording` w żądaniu."""
        from core.models.base_game_camera import HDMI_TO_DEVICE
        assigned = data.get('assigned', []) or []
        try:
            new_devices = {HDMI_TO_DEVICE[int(item['hdmi_input'])] for item in assigned}
        except (KeyError, TypeError, ValueError):
            return 400, {'error': 'Nieprawidłowe wejście HDMI na liście kamer'}
        if MAIN_CAMERA not in new_devices:
            return 400, {'error': 'Kamera główna (wejście HDMI 1) jest zawsze włączona — nie można jej odznaczyć'}

        from core.managers import session_manager
        if game_id != session_manager.current_game_id():
            return None   # mecz inny niż bieżący: kamery nie działają, nic nie nagrywa
        from core.managers.game_camera_manager import GameCameraManager
        old_devices = {gc.device_name for gc in GameCameraManager().get_cameras_for_game(game_id)}
        recording = sorted(d for d in (old_devices - new_devices) if self.is_camera_recording(d))
        if recording and not data.get('confirm_stop_recording'):
            return 409, {'confirm_required': True, 'cameras': recording,
                         'error': 'Kamera nagrywa: usunięcie zakończy jej nagranie. Potwierdź, aby kontynuować.'}
        return None

    def after_camera_assignment_saved(self, data):
        """Po zapisie kamer w opcjach meczu: zmiana działa natychmiast (kamery włączają się i wyłączają od razu)."""
        self.sync_cameras(stop_recording_for_removed=bool(data.get('confirm_stop_recording')))

    # ── zdarzenia z pluginu ──────────────────────────────────────────────────

    def on_camera_state(self, msg):
        """camera_state: zmiana stanu odbioru kamery (także zdarzenie po `cameras_status`)."""
        payload = msg.get('payload') or {}
        camera_id = payload.get('camera_id')
        if not camera_id:
            return
        sup = self._sup()
        with sup['lock']:
            prev = sup['cameras'].get(camera_id, {})
            info = {
                'state': payload.get('state', STATE_OFF),
                'wanted': bool(payload.get('wanted')),
                'recording': bool(payload.get('recording')),
                'streaming': bool(payload.get('streaming')),
                'error': payload.get('error'),
            }
            sup['cameras'][camera_id] = info
        current_app.logger.info(f'📷 {camera_id}: {info["state"]} wanted={info["wanted"]} recording={info["recording"]} {info["error"] or ""}')

        if info['state'] == STATE_RUNNING and prev.get('state') != STATE_RUNNING:
            self._camera_running(camera_id)
        elif not info['wanted'] and prev.get('wanted'):
            self._clear_camera_source(camera_id)
        self._refresh_camera_notices()
        self._emit_camera_states()

    def on_set_active_cameras_response(self, msg):
        payload = msg.get('payload') or {}
        if payload.get('status') != 'ok':
            current_app.logger.error(f'📷 Plugin odrzucił listę kamer: {payload.get("error")}')
            sup = self._sup()
            with sup['lock']:
                sup['last_sent'] = None   # następna zmiana wyśle listę ponownie
            self._emit_to_ui('camera_assignment_error', {'error': payload.get('error')})
            return
        cameras = payload.get('cameras') or {}
        sup = self._sup()
        with sup['lock']:
            for camera_id, info in cameras.items():
                sup['cameras'][camera_id] = {
                    'state': info.get('state', STATE_OFF), 'wanted': bool(info.get('wanted')),
                    'recording': bool(info.get('recording')), 'streaming': bool(info.get('streaming')),
                    'error': info.get('error'),
                }
        blocked = payload.get('blocked') or []
        if blocked:
            current_app.logger.warning(f'📷 Plugin nie wyłączył nagrywających kamer bez potwierdzenia: {blocked}')
            self._emit_to_ui('camera_remove_blocked', {'cameras': blocked})
        self._refresh_camera_notices()
        self._emit_camera_states()

    def on_recording_interrupted(self, msg):
        """Nagrywanie trwa jako sesja, ale bieżący segment zamknięto (utrata obrazu lub awaria procesu): pasek „przerwa w nagraniu”."""
        payload = msg.get('payload') or {}
        camera_id = payload.get('camera_id')
        if not camera_id:
            return
        sup = self._sup()
        with sup['lock']:
            sup['interrupted'][camera_id] = payload.get('reason') or 'unknown'
        current_app.logger.warning(f'📷 {camera_id}: przerwa w nagraniu ({payload.get("reason")})')
        self._refresh_camera_notices()
        self._emit_camera_states()

    def on_stream_changed(self, msg):
        """Podgląd SRT kamery wystartował lub padł. Start: źródło w OBS łączy się od nowa (nasłuch SRT powstał dopiero teraz)."""
        payload = msg.get('payload') or {}
        camera_id = payload.get('camera_id')
        if camera_id and payload.get('active') and self._camera_managed(camera_id):
            self._set_and_restart_source(camera_id)

    def _clear_interrupted(self, camera_id):
        sup = self._sup()
        with sup['lock']:
            changed = sup['interrupted'].pop(camera_id, None) is not None
        if changed:
            self._refresh_camera_notices()
            self._emit_camera_states()

    # ── źródła sCameraN w OBS ────────────────────────────────────────────────

    def _camera_managed(self, camera_id):
        """Kamera jest na liście pluginu: jej źródło w OBS prowadzi nadzór kamer (inaczej zostaje dawna zasada: nagrywanie)."""
        sup = self._sup()
        with sup['lock']:
            return bool(sup['cameras'].get(camera_id, {}).get('wanted'))

    def _obs(self):
        from core.managers import get_obs_ws_manager
        return get_obs_ws_manager()

    def _camera_running(self, camera_id):
        """„Kamera N działa”: URL SRT źródła i odświeżenie go w OBS."""
        self._set_and_restart_source(camera_id)

    def _set_and_restart_source(self, camera_id):
        if not self.recorder_plugin_ip:
            current_app.logger.warning(f'📷 {camera_id}: brak adresu recorder-pluginu — źródło OBS zostanie ustawione po jego zgłoszeniu')
            return
        try:
            obs = self._obs()
            obs.set_camera_stream_url(camera_id, self.recorder_plugin_ip)
            obs.restart_camera_stream_source(camera_id)
        except Exception as e:
            current_app.logger.error(f'Nie udało się odświeżyć źródła OBS kamery {camera_id}: {e}')

    def _clear_camera_source(self, camera_id):
        try:
            self._obs().set_camera_stream_url(camera_id, None)
        except Exception as e:
            current_app.logger.error(f'Nie udało się wyczyścić źródła OBS kamery {camera_id}: {e}')

    def apply_camera_sources(self):
        """Po zgłoszeniu adresu pluginu: źródła kamer, które już działają."""
        sup = self._sup()
        with sup['lock']:
            running = [cid for cid, info in sup['cameras'].items() if info.get('state') == STATE_RUNNING and info.get('wanted')]
        for camera_id in running:
            self._set_and_restart_source(camera_id)

    # ── paski w panelu i stan dla opcji meczu ────────────────────────────────

    NOTICE_PREFIX = 'camera-'

    def camera_notice_text(self, camera_id, info, interrupted):
        """Tekst paska kamery albo None. Tylko kamery z listy; „startuje” nie jest problemem."""
        if not info.get('wanted'):
            return None
        label = f'KAMERA {camera_number(camera_id)}'
        if interrupted:
            return f'{label}: przerwa w nagraniu (brak obrazu)', 'error'
        if info.get('state') == STATE_ERROR:
            if info.get('recording'):
                return f'{label}: nagrywa wprost, bez podglądu w OBS', 'warning'
            return f'{label}: brak obrazu', 'error'
        return None

    def _refresh_camera_notices(self):
        try:
            from core.managers import get_service_notices
            notices = get_service_notices()
        except Exception:
            return
        sup = self._sup()
        with sup['lock']:
            cameras = {cid: dict(info) for cid, info in sup['cameras'].items()}
            interrupted = dict(sup['interrupted'])
        for camera_id, info in cameras.items():
            key = f'{self.NOTICE_PREFIX}{camera_id}'
            result = self.camera_notice_text(camera_id, info, interrupted.get(camera_id))
            if result:
                notices.set(key, result[0], result[1])
            else:
                notices.clear(key)
        # kamery, o których plugin już nie raportuje (rozłączenie): zdejmij paski
        known = {f'{self.NOTICE_PREFIX}{cid}' for cid in cameras}
        for notice in notices.snapshot():
            if notice['key'].startswith(self.NOTICE_PREFIX) and notice['key'] not in known:
                notices.clear(notice['key'])

    def _emit_camera_states(self):
        self._emit_to_ui('camera_states', {'cameras': self.camera_states(), 'wanted': self.wanted_cameras()})
