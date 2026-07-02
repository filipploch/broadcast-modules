"""Servo Manager — pan/tilt control for cam-head ESP32 plugins"""
from flask import current_app


class ServoManager:
    """Manages MG90S pan/tilt servo heads (cam-head-* plugins)."""

    def __init__(self, hub_client):
        self.hub_client = hub_client
        # head_id → {'pan': int, 'tilt': int, 'online': bool}
        self._heads: dict = {}

    # ── Plugin lifecycle ──────────────────────────────────────────────────────

    def on_head_online(self, head_id: str):
        self._heads.setdefault(head_id, {'pan': 90, 'tilt': 90, 'online': False})
        self._heads[head_id]['online'] = True
        current_app.logger.info(f"[servo] Head online: {head_id}")
        self.hub_client.send_to_plugin(head_id, 'get_status', {})
        self._emit('servo_head_online', {'head_id': head_id})

    def on_head_offline(self, head_id: str):
        if head_id in self._heads:
            self._heads[head_id]['online'] = False
        current_app.logger.warning(f"[servo] Head offline: {head_id}")
        self._emit('servo_head_offline', {'head_id': head_id})

    # ── Commands ──────────────────────────────────────────────────────────────

    def set_pan_tilt(self, head_id: str, pan: int, tilt: int):
        pan  = max(0, min(180, int(pan)))
        tilt = max(0, min(180, int(tilt)))
        self.hub_client.send_to_plugin(head_id, 'pan_tilt', {'pan': pan, 'tilt': tilt})
        if head_id in self._heads:
            self._heads[head_id].update({'pan': pan, 'tilt': tilt})

    def center(self, head_id: str):
        self.hub_client.send_to_plugin(head_id, 'center', {})

    def center_all(self):
        for head_id, info in self._heads.items():
            if info['online']:
                self.center(head_id)

    # ── Incoming messages ─────────────────────────────────────────────────────

    def on_servo_status(self, msg: dict):
        payload = msg.get('payload', {})
        head_id = payload.get('id') or msg.get('from', '')
        pan     = payload.get('pan', 99)
        tilt    = payload.get('tilt', 79)
        if head_id in self._heads:
            self._heads[head_id].update({'pan': pan, 'tilt': tilt})
        self._emit('servo_status', {'head_id': head_id, 'pan': pan, 'tilt': tilt})

    # ── Status ────────────────────────────────────────────────────────────────

    def get_heads(self) -> list:
        return [{'head_id': hid, **info} for hid, info in self._heads.items()]

    # ── Internal ─────────────────────────────────────────────────────────────

    def _emit(self, event: str, data: dict):
        try:
            from core.extensions import socketio
            socketio.emit(event, data)
        except Exception as e:
            current_app.logger.error(f"[servo] emit failed: {e}")
