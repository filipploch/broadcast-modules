"""EDL builder for camera replays that may span multiple recording segments.

mpv's "# mpv EDL v0" format lets it treat several real files as one seekable
virtual timeline without physically concatenating them (see mpv's
DOCS/edl-mpv.rst). We generate a small .edl file per replay request instead
of always pointing replay-plugin at a single raw .mkv, so a replay window
that straddles a segment-rotation boundary (e.g. an event recorded right
after an early cut — see mark_segment_end) still plays as one continuous
clip. replay_sequence()/replay-plugin need no changes for this: an .edl path
just IS the "video_path" as far as they're concerned — mpv opens it exactly
like a real file.
"""
import os
from datetime import datetime, timedelta
from flask import current_app


def _edl_dir():
    """Local (not Samba) directory shared by main-module and replay-plugin —
    both run on the same Windows machine, so no network round trip is needed
    for these tiny control-plane files. Deliberately NOT on R:\\recorder:
    writing there would add extra load/SMB traffic to the already-loaded
    Debian recorder host for no benefit.
    """
    path = current_app.config.get('REPLAY_EDL_DIR', r'C:\BroadcastTemp\replay-edl')
    os.makedirs(path, exist_ok=True)
    return path


def build_replay_context(event_camera):
    """Given an EventCamera row, return a dict shaped exactly like the
    {'video_path', 'replay_start_time', 'replay_end_time'} context that
    replay_sequence() already expects. video_path points at a freshly
    written .edl file — used uniformly whether the window covers one
    segment or several, so there's only one shape for callers to handle.

    Falls back to the EventCamera row's own (raw file, ms offsets) on any
    lookup failure, so a replay click never hard-fails because of this —
    it just loses the "spans a rotation boundary" benefit for that click.
    """
    fallback = {
        'video_path': event_camera.video_path,
        'replay_start_time': event_camera.replay_start_time,
        'replay_end_time': event_camera.replay_end_time,
    }

    try:
        from core.models.base_camera_recording_segment import get_camera_recording_segment_model
        from core.models.base_game_camera import get_game_camera_model
        from core.models.base_game_event import get_game_event_model

        CameraRecordingSegment = get_camera_recording_segment_model()
        GameCamera = get_game_camera_model()
        GameEvent = get_game_event_model()

        game_event = GameEvent.query.get(event_camera.game_event_id)
        if not game_event:
            return fallback

        game_camera = GameCamera.query.filter_by(
            game_id=game_event.game_id, camera_id=event_camera.camera_id
        ).first()
        if not game_camera:
            return fallback
        recorder_camera_id = game_camera.device_name  # "camera1".."camera4"

        # video_path stored on EventCamera ("R:/recorder/<file>.mkv") is
        # whichever segment was open AT EVENT-CREATION TIME; replay_start_time/
        # replay_end_time are ms OFFSETS INTO THAT FILE, not wall-clock — see
        # RecorderManager._on_record_status. Anchor them to that segment's own
        # started_at to get real wall-clock instants we can range-search with.
        anchor_file_name = os.path.basename(event_camera.video_path)
        anchor_segment = (CameraRecordingSegment.query
                          .filter_by(recorder_camera_id=recorder_camera_id,
                                     game_id=game_event.game_id,
                                     file_name=anchor_file_name)
                          .first())
        if not anchor_segment:
            return fallback

        wall_start = anchor_segment.started_at + timedelta(milliseconds=event_camera.replay_start_time)
        wall_end   = anchor_segment.started_at + timedelta(milliseconds=event_camera.replay_end_time)

        segments = CameraRecordingSegment.find_range(
            recorder_camera_id, game_event.game_id, wall_start, wall_end
        )
        if not segments:
            return fallback

        lines = ["# mpv EDL v0"]
        total_seconds = 0.0
        for i, seg in enumerate(segments):
            seg_window_start = max(wall_start, seg.started_at)
            offset_s = (seg_window_start - seg.started_at).total_seconds()
            is_last = (i == len(segments) - 1)

            if is_last:
                length_s = (wall_end - seg_window_start).total_seconds()
                if length_s <= 0:
                    continue
                lines.append(f"{seg.file_path},{offset_s:.3f},{length_s:.3f}")
                total_seconds += length_s
            else:
                # Odtwarzaj do naturalnego końca TEGO segmentu — pomiń "length"
                # w linii EDL (spec: brak length = "estimated remaining
                # duration of source file"). length_s tu tylko na potrzeby
                # zsumowania total_seconds zwracanego wywołującemu.
                seg_end = seg.ended_at or datetime.utcnow()
                length_s = (seg_end - seg_window_start).total_seconds()
                if length_s <= 0:
                    continue
                lines.append(f"{seg.file_path},{offset_s:.3f}")
                total_seconds += length_s

        if len(lines) <= 1:
            return fallback

        edl_path = os.path.join(_edl_dir(), f"event_camera_{event_camera.id}.edl")
        with open(edl_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")

        return {
            'video_path': edl_path,
            'replay_start_time': 0,
            'replay_end_time': int(total_seconds * 1000),
        }
    except Exception as e:
        current_app.logger.error(f"build_replay_context failed for event_camera {event_camera.id}: {e}")
        return fallback
