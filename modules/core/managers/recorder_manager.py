"""Recorder Manager - Manages camera recording"""
from flask import current_app


def _get_camera():
    from core.models.base_camera import get_camera_model
    return get_camera_model()

def _get_event_camera():
    from core.models.base_event_camera import get_event_camera_model
    return get_event_camera_model()

class RecorderManager:
    """Manages recorder plugin and camera recording"""
    
    def __init__(self, hub_client):
        self.hub_client = hub_client
        self.is_recording = False
        self.recorder_plugin_id = 'recorder-plugin'
        self.recorder_plugin_ip = None  # ostatnie zgłoszone IP — patrz on_recorder_plugin_info

    def on_recorder_online(self):
        """Called when recorder plugin comes online"""
        current_app.logger.info("📹 Recorder plugin online - configuring cameras")
        
        # Get enabled cameras
        cameras = self._get_enabled_cameras()
        
        # Send configuration to recorder
        self.hub_client.send_to_plugin(self.recorder_plugin_id, 'configure_cameras', {'cameras': cameras})
        self.hub_client.send_to_plugin(self.recorder_plugin_id, 'recording_status', {})
        
        # Check if we should be recording (based on OBS status)
        # TODO: Query OBS status and sync
        # For now, just log
        current_app.logger.info(f"Recorder configured with {len(cameras)} cameras")

    # recorder_manager.py
    def on_recording_status_received(self, msg):
        payload = msg.get('payload', {})
        cameras = payload.get('cameras', {})
        active = [cam_id for cam_id, active in cameras.items() if active]
        current_app.logger.info(f"📹 Recording status: {cameras}")
        self._emit_to_ui('recording_status_response', {
            'cameras': cameras,
            'active_cameras': active,
            'any_recording': bool(active),
            })
        
    def on_recording_command_response(self, msg):
        payload = msg.get('payload', {})
        request_type = payload.get('requestType')
        if request_type == 'StartRecord':
            cameras = payload.get('cameras', {})
            for camera_id, cam_info in cameras.items():
                if cam_info.get('succes') and cam_info.get('is_recording'):
                    self._emit_to_ui('recording_started', {'camera_id': camera_id})
        elif request_type == 'StopRecord':
            cameras = payload.get('cameras', {})
            for camera_id, cam_info in cameras.items():
                if cam_info.get('succes') and not cam_info.get('is_recording'):
                    self._emit_to_ui('recording_stopped', {'camera_id': camera_id})
        elif request_type == 'GetRecordStatus':
            request_id = payload.get('request_id')
            if request_id.startswith('get-record-status-'):
                payload['request_id'] = request_id.split('get-record-status-')[1]
                self._on_record_status(payload)
                # TODO
            elif request_id.startswith('rec-status-'):
                cameras = payload.get('cameras')
                self._emit_to_ui('recording_status_updated', cameras)

    def _on_record_status(self, payload):

        
        from core.extensions import db

        cameras = payload.get('cameras')
        game_event_id = payload.get('request_id')
        

        # if not all([game_event_id, camera_id, video_path, replay_end_time is not None]):
        #     self._log('warning', f'_on_record_file_info: incomplete payload: {payload}')
        #     return

        for camera in cameras:
            try:
                EventCamera = _get_event_camera()
                _camera = cameras.get(camera)
                file_name    = _camera.get('file_name')
                video_path = 'R:/recorder/' + file_name
                replay_end_time   = _camera.get('output_duration')
                replay_start_time = EventCamera.calc_replay_start_time(replay_end_time) if replay_end_time is not None else 0

                existing = EventCamera.query.filter_by(
                    game_event_id=game_event_id,
                    camera_id=camera
                ).first()

                if existing:
                    existing.video_path = video_path
                    existing.replay_start_time = replay_start_time
                    existing.replay_end_time = replay_end_time
                else:
                    ec = EventCamera(
                        game_event_id=game_event_id,
                        camera_id=camera,
                        video_path=video_path,
                        replay_start_time=replay_start_time,
                        replay_end_time=replay_end_time,
                    )
                    db.session.add(ec)

                db.session.commit()
                current_app.logger.info(f'✅ EventCamera saved: game_event_id={game_event_id} camera_id={camera}')

            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f'❌ Failed to save EventCamera: {e}')
    
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
        Camera = _get_camera()
        cameras = Camera.query.filter_by(is_enabled=True).order_by(Camera.priority).all()
        return [cam.recorder_camera_id for cam in cameras if cam.recorder_camera_id]
    
    def on_recording_started(self, msg):
        """Called by hub_client when recorder-plugin reports recording started for a camera.

        Persists a camera_recording_segment (module-specific — silently
        skipped for modules that don't register that model, e.g. futsal_nalf)
        so a later "what was recording at match time T" lookup is possible.
        started_at is stamped as datetime.utcnow() (server receipt time), not
        parsed from the plugin's self-reported started_at — see
        base_camera_recording_segment.py for why.
        """
        from datetime import datetime
        payload = msg.get('payload', {})
        camera_id = payload.get('camera_id')
        current_app.logger.info(f"▶️  Recording started: {camera_id} → {payload.get('file_name')}")

        reported_started_at = None
        started_at_ms = payload.get('started_at')
        if started_at_ms:
            try:
                reported_started_at = datetime.utcfromtimestamp(int(started_at_ms) / 1000)
            except (TypeError, ValueError):
                current_app.logger.warning(f"recording_started: invalid started_at={started_at_ms!r}")

        try:
            from core.models.base_camera_recording_segment import get_camera_recording_segment_model
            CameraRecordingSegment = get_camera_recording_segment_model()
            match_id  = payload.get('match_id') or None
            period_id = payload.get('period_id') or None
            CameraRecordingSegment.start_segment(
                recorder_camera_id=camera_id,
                game_id=int(match_id) if match_id else None,
                period_id=int(period_id) if period_id else None,
                file_name=payload.get('file_name'),
                file_path=payload.get('file_path'),
                reported_started_at=reported_started_at,
            )
        except RuntimeError:
            pass  # moduł nie rejestruje tego modelu — funkcja niedostępna, nic do zrobienia
        except Exception as e:
            current_app.logger.error(f"Failed to persist camera_recording_segment (start): {e}")

        self._emit_to_ui('recording_started', {
            'camera_id':   camera_id,
            'camera_name': payload.get('camera_name'),
            'file_name':   payload.get('file_name'),
            'file_path':   payload.get('file_path'),
            'started_at':  payload.get('started_at'),
            'match_id':    payload.get('match_id'),
            'period_id':   payload.get('period_id'),
        })

        # Point this camera's OBS source at its SRT stream only now that
        # there's actually something listening on the other end — see
        # on_recording_stopped for why it gets cleared again below.
        self._set_camera_stream_active(camera_id, True)

    def on_recording_stopped(self, msg):
        """Called by hub_client when recorder-plugin reports recording stopped for a camera."""
        payload = msg.get('payload', {})
        camera_id = payload.get('camera_id')
        current_app.logger.info(f"⏹️  Recording stopped: {camera_id}")

        try:
            from core.models.base_camera_recording_segment import get_camera_recording_segment_model
            CameraRecordingSegment = get_camera_recording_segment_model()
            CameraRecordingSegment.close_open_segment(camera_id)
        except RuntimeError:
            pass
        except Exception as e:
            current_app.logger.error(f"Failed to persist camera_recording_segment (stop): {e}")

        self._emit_to_ui('recording_stopped', {
            'camera_id': camera_id,
        })

        # Recording stopped means recorder-plugin's StreamManager stops too
        # (its SRT listener only runs while the camera is recording — see
        # StreamManager.StartStream) — clear the OBS source's URL so it
        # isn't left retrying a connection to nothing every ~10s until the
        # camera starts recording again.
        self._set_camera_stream_active(camera_id, False)

    def _set_camera_stream_active(self, camera_id, active):
        try:
            from core.managers import get_obs_ws_manager
            obs = get_obs_ws_manager()
            obs.set_camera_stream_url(camera_id, self.recorder_plugin_ip if active else None)
        except Exception as e:
            current_app.logger.error(f"Failed to update camera stream source for {camera_id}: {e}")

    def on_recorder_plugin_info(self, msg):
        """Called when recorder-plugin reports its own IP (sent once right
        after registering with the hub — see main.go's "registered" case).
        Only caches the IP — it's applied to a camera's sCameraN source when
        that camera actually starts recording (_set_camera_stream_active),
        not here, so a source with nothing listening on the other end isn't
        left retrying a connection every ~10s for as long as recorder-plugin
        stays connected but idle. A camera already recording when this
        arrives (e.g. main-module restarted mid-match) keeps whatever URL
        its source already had until its next start/stop — use
        resync_camera_stream_sources to force it sooner.
        """
        payload = msg.get('payload', {})
        ip = payload.get('ip')
        if not ip:
            return
        current_app.logger.info(f"📍 recorder-plugin reported IP: {ip}")
        self.recorder_plugin_ip = ip

    def resync_camera_stream_sources(self):
        """Re-applies the last known recorder-plugin IP to the sCameraN
        sources on demand — for manual troubleshooting (e.g. after editing
        this code, without waiting for recorder-plugin to reconnect)."""
        if not self.recorder_plugin_ip:
            current_app.logger.warning("resync_camera_stream_sources: no recorder-plugin IP known yet")
            return
        self._sync_camera_stream_sources(self.recorder_plugin_ip)

    def _sync_camera_stream_sources(self, ip):
        try:
            from core.managers import get_obs_ws_manager
            get_obs_ws_manager().sync_camera_stream_sources(ip)
        except Exception as e:
            current_app.logger.error(f"Failed to sync camera stream sources: {e}")

    def on_segment_rotated(self, msg):
        """Called when recorder-plugin rotates a camera's recording segment.
        Rotating the segment briefly restarts that camera's ffmpeg process,
        which also writes the v4l2loopback device the SRT stream reads from —
        so the loopback write side drops out for a moment, the streaming
        ffmpeg crashes/restarts with a fresh listening socket, and OBS's
        existing connection to the old socket is left dead (its Media Source
        has restart_on_activate off, so it never redials on its own).
        Restarting the matching sCameraN input in OBS right after forces it
        to reconnect to the new socket, instead of the picture going dark
        after every rotation (every 15-20 min by default).
        """
        payload = msg.get('payload', {})
        camera_id = payload.get('camera_id')
        if not camera_id:
            return
        current_app.logger.info(f"🔁 Segment rotated for {camera_id} — restarting matching OBS source")
        try:
            from core.managers import get_obs_ws_manager
            get_obs_ws_manager().restart_camera_stream_source(camera_id)
        except Exception as e:
            current_app.logger.error(f"Failed to restart camera stream source for {camera_id}: {e}")

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
            from core.extensions import socketio
            # socketio.emit(event, data, broadcast=True)
            socketio.emit(msg_type, data)
        except Exception as e:
            current_app.logger.error(f"Failed to emit to UI: {e}")