"""GoPro Manager — GoPro Hero 4 bridge via cam-head ESP32 plugins"""
from flask import current_app


class GoProManager:
    """
    Receives GoPro status from cam-head plugins and sends commands to them.
    Each cam-head running in GOPRO_ONLY or FULL mode sends gopro_status
    via broadcast:gopro_events after each WiFi session with the camera.
    """

    def __init__(self, hub_client):
        self.hub_client = hub_client
        # head_id → state dict
        self._devices: dict = {}

    # ── Plugin lifecycle ──────────────────────────────────────────────────────

    def on_head_online(self, head_id: str):
        self._devices.setdefault(head_id, {'valid': False})
        current_app.logger.info(f"[gopro] Head online: {head_id}")

    def on_head_offline(self, head_id: str):
        if head_id in self._devices:
            self._devices[head_id]['valid'] = False
        current_app.logger.warning(f"[gopro] Head offline: {head_id}")
        self._emit('gopro_head_offline', {'head_id': head_id})

    # ── Incoming messages ─────────────────────────────────────────────────────

    def on_gopro_status(self, msg: dict):
        payload = msg.get('payload', {})
        head_id = payload.get('id') or msg.get('from', '')
        state = {
            'recording':      payload.get('recording', False),
            'battery':        payload.get('battery', -1),
            'mode':           payload.get('mode', 0),
            'sd_ok':          payload.get('sd_ok', False),
            'remaining_secs': payload.get('remaining_secs', 0),
            'valid':          payload.get('valid', False),
        }
        self._devices[head_id] = state
        self._emit('gopro_status', {'head_id': head_id, **state})

    def on_gopro_result(self, msg: dict):
        payload = msg.get('payload', {})
        head_id = payload.get('id') or msg.get('from', '')
        self._emit('gopro_result', {
            'head_id': head_id,
            'cmd':     payload.get('cmd'),
            'success': payload.get('success', False),
            'error':   payload.get('error', ''),
        })

    # ── Commands ──────────────────────────────────────────────────────────────

    def send_command(self, head_id: str, cmd: str, **kwargs):
        """Send a GoPro command to a specific cam-head plugin."""
        self.hub_client.send_to_plugin(head_id, 'gopro_cmd', {'cmd': cmd, **kwargs})

    def shutter_start(self, head_id: str):
        self.send_command(head_id, 'shutter_start')

    def shutter_stop(self, head_id: str):
        self.send_command(head_id, 'shutter_stop')

    def request_status(self, head_id: str):
        self.send_command(head_id, 'get_status')

    def set_video_mode(self, head_id: str):
        self.send_command(head_id, 'mode_video')

    def set_photo_mode(self, head_id: str):
        self.send_command(head_id, 'mode_photo')

    # ── Status ────────────────────────────────────────────────────────────────

    def get_devices(self) -> list:
        return [{'head_id': hid, **state} for hid, state in self._devices.items()]

    def get_device(self, head_id: str) -> dict | None:
        return self._devices.get(head_id)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _emit(self, event: str, data: dict):
        try:
            from core.extensions import socketio
            socketio.emit(event, data)
        except Exception as e:
            current_app.logger.error(f"[gopro] emit failed: {e}")
