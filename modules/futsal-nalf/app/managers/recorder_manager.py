"""Recorder Manager - Manages camera recording"""
from flask import current_app
from app.models import Camera

class RecorderManager:
    """Manages recorder plugin and camera recording"""
    
    def __init__(self, hub_client):
        self.hub_client = hub_client
        self.is_recording = False
        self.recorder_plugin_id = 'recorder'
        
    def on_recorder_online(self):
        """Called when recorder plugin comes online"""
        current_app.logger.info("📹 Recorder plugin online - configuring cameras")
        
        # Get enabled cameras
        cameras = self._get_enabled_cameras()
        
        # Send configuration to recorder
        self.hub_client.send_to_plugin(
            self.recorder_plugin_id,
            'configure_cameras',
            {
                'cameras': cameras
            }
        )
        
        # Check if we should be recording (based on OBS status)
        # TODO: Query OBS status and sync
        # For now, just log
        current_app.logger.info(f"Recorder configured with {len(cameras)} cameras")
    
    def start_recording(self):
        """Start camera recording"""
        if self.is_recording:
            current_app.logger.warning("⚠️  Recording already active")
            return {'status': 'already_recording'}
        
        cameras = self._get_enabled_cameras()
        
        current_app.logger.info(f"🔴 Starting recording for {len(cameras)} cameras")
        
        # Send to recorder plugin
        self.hub_client.send_to_plugin(
            self.recorder_plugin_id,
            'start_recording',
            {
                'cameras': cameras
            }
        )

        
        
        self.is_recording = True
        
        return {
            'status': 'recording_started',
            'cameras': cameras
        }
    
    def stop_recording(self):
        """Stop camera recording"""
        if not self.is_recording:
            current_app.logger.warning("⚠️  Recording not active")
            return {'status': 'not_recording'}
        
        current_app.logger.info("⏹️  Stopping recording")
        
        # Send to recorder plugin
        self.hub_client.send_to_plugin(
            self.recorder_plugin_id,
            'stop_recording',
            {}
        )
        
        self.is_recording = False
        
        return {'status': 'recording_stopped'}
    
    def add_marker(self, marker_type, data=None):
        """Add marker to recording"""
        if not self.is_recording:
            return {'error': 'Not recording'}
        
        current_app.logger.info(f"📍 Adding marker: {marker_type}")
        
        # Send to recorder plugin
        self.hub_client.send_to_plugin(
            self.recorder_plugin_id,
            'add_marker',
            {
                'marker_type': marker_type,
                'data': data or {}
            }
        )
        
        return {'status': 'marker_added', 'type': marker_type}
    
    def _get_enabled_cameras(self):
        """Get list of enabled camera IDs"""
        cameras = Camera.query.filter_by(is_enabled=True).order_by(Camera.priority).all()
        return [cam.recorder_camera_id for cam in cameras if cam.recorder_camera_id]
    
    def on_recording_started(self, msg):
        """Called by hub_client when recorder-plugin reports recording started for a camera."""
        payload = msg.get('payload', {})
        camera_id = payload.get('camera_id')
        current_app.logger.info(f"▶️  Recording started: {camera_id} → {payload.get('file_name')}")
        self._emit_to_ui('recording_started', {
            'camera_id':   camera_id,
            'camera_name': payload.get('camera_name'),
            'file_name':   payload.get('file_name'),
            'file_path':   payload.get('file_path'),
            'started_at':  payload.get('started_at'),
            'match_id':    payload.get('match_id'),
            'period_id':   payload.get('period_id'),
        }, broadcast=True)

    def on_recording_stopped(self, msg):
        """Called by hub_client when recorder-plugin reports recording stopped for a camera."""
        payload = msg.get('payload', {})
        camera_id = payload.get('camera_id')
        current_app.logger.info(f"⏹️  Recording stopped: {camera_id}")
        self._emit_to_ui('recording_stopped', {
            'camera_id': camera_id,
        }, broadcast=True)
    
    def get_camera_status(self):
        """Get recording status"""
        cameras = self._get_enabled_cameras()
        
        return {
            'is_recording': self.is_recording,
            'cameras': cameras,
            'camera_count': len(cameras)
        }
    
    def _emit_to_ui(self, msg_type, data):
        """Emit event to UI clients via SocketIO"""
        try:
            from app.extensions import socketio
            # socketio.emit(event, data, broadcast=True)
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f"Failed to emit to UI: {e}")