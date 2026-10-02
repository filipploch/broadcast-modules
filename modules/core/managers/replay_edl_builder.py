"""EDL builder that joins ALL of a camera's recording segments (for one
game) into a single virtual timeline.

mpv's "# mpv EDL v0" format lets it treat several real files as one seekable
virtual timeline without physically concatenating them (see mpv's
DOCS/edl-mpv.rst). Segments rotate frequently now (every game event, min
20s — see mark_segment_end), so a camera's recording for a game is always
split across many real .mkv files. Rather than only bridging the narrow
window a single replay needs, we always build the EDL from EVERY segment
recorded so far for that camera+game — the whole recording behaves as one
continuous virtual file, and any replay's start/end offsets are expressed
against that single timeline. replay_sequence()/replay-plugin need no
changes for this: an .edl path just IS the "video_path" as far as they're
concerned — mpv opens it exactly like a real file.
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

    Default resolved relative to current_app.root_path (modules/<module>/app),
    same pattern as REPLAY_PLUGIN_CONFIG in sequences.py — repo-root/modules/temp
    is already covered by .gitignore's **/temp/** so these never get committed.
    """
    path = current_app.config.get(
        'REPLAY_EDL_DIR',
        os.path.abspath(os.path.join(current_app.root_path, '..', '..', '..', 'modules', 'temp', 'replay-edl'))
    )
    os.makedirs(path, exist_ok=True)
    return path


def build_replay_context(event_camera):
    """Given an EventCamera row, return a dict shaped exactly like the
    {'video_path', 'replay_start_time', 'replay_end_time'} context that
    replay_sequence() already expects. video_path points at a freshly
    written .edl file joining EVERY segment recorded so far for that
    camera+game into one virtual timeline — not just the segments the
    requested window happens to touch — so scrubbing/replaying anywhere
    in the game always behaves as one continuous file, regardless of how
    many times the segment has rotated.

    Falls back to the EventCamera row's own (raw file, ms offsets) on any
    lookup failure, so a replay click never hard-fails because of this —
    it just loses the "seamless across rotations" benefit for that click.
    """
    fallback = {
        'video_path': event_camera.video_path,
        'replay_start_time': event_camera.replay_start_time,
        'replay_end_time': event_camera.replay_end_time,
    }

    try:
        from core.models.base_camera_recording_segment import get_camera_recording_segment_model
        from core.models.base_game_event import get_game_event_model

        CameraRecordingSegment = get_camera_recording_segment_model()
        GameEvent = get_game_event_model()

        game_event = GameEvent.query.get(event_camera.game_event_id)
        if not game_event:
            return fallback

        # EventCamera.camera_id is declared as an Integer FK to cameras.id,
        # but RecorderManager._on_record_status actually stores the recorder
        # device-slot STRING there ("camera1".."camera4" — the dict key from
        # recorder-plugin's GetRecordStatus response), not a cameras.id value
        # — SQLite stores it silently since it isn't a STRICT table. That
        # string IS already what CameraRecordingSegment.recorder_camera_id
        # needs, so use it directly instead of round-tripping through
        # GameCamera.device_name (which compares Integer to this string and
        # never matches, silently forcing the fallback below every time).
        recorder_camera_id = event_camera.camera_id

        # video_path stored on EventCamera ("R:/recorder/<file>.mkv") is
        # whichever segment was open AT EVENT-CREATION TIME; replay_start_time/
        # replay_end_time are ms OFFSETS INTO THAT FILE, not wall-clock — see
        # RecorderManager._on_record_status. Anchor them to that segment's own
        # started_at to get real wall-clock instants we can locate on the
        # full timeline built below.
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

        # Whole history for this camera+game, not just what the window
        # touches — this is what makes the join unconditional ("always"),
        # rather than only kicking in when a single event's window happens
        # to straddle a rotation.
        segments = CameraRecordingSegment.all_for_camera_game(recorder_camera_id, game_event.game_id)
        if not segments:
            return fallback

        now = datetime.utcnow()
        lines = ["# mpv EDL v0"]
        cumulative_ms = 0.0
        start_offset_ms = None
        end_offset_ms = None
        for seg in segments:
            # camera_recording_segments outlives the actual files — R:\recorder\
            # gets cleaned up on the Debian side (disk space), but the DB rows
            # aren't pruned along with it. Joining a segment whose file is
            # gone breaks mpv's EDL load entirely (fails on the first missing
            # entry, nothing plays) — so only join what's still actually
            # there instead of blindly trusting the DB history.
            mapped_path = f"R:/recorder/{seg.file_name}"
            if not os.path.exists(mapped_path):
                continue

            seg_end = seg.ended_at or now
            duration_s = max(0.0, (seg_end - seg.started_at).total_seconds())
            duration_ms = duration_s * 1000

            # Długość podajemy jawnie dla każdego ZAMKNIĘTEGO segmentu — znamy
            # ją dokładnie z ended_at-started_at. Bez tego mpv musiałby przy
            # ładowaniu otworzyć/wysondować KAŻDY plik po SMB żeby ustalić
            # jego długość, zanim zbuduje oś czasu — przy kilkudziesięciu
            # segmentach meczu to potrafiło przekroczyć 10s timeout na
            # 'replay_started' (patrz replay_sequence). Z podaną długością
            # mpv buduje oś z samego tekstu EDL, bez I/O po sieci. Tylko
            # ostatni (wciąż otwarty/rosnący) segment zostaje bez length —
            # dla niego długość faktycznie nie jest jeszcze znana.
            if seg.ended_at is not None:
                lines.append(f"{mapped_path},0,{duration_s:.3f}")
            else:
                lines.append(f"{mapped_path},0")

            if start_offset_ms is None and seg.started_at <= wall_start <= seg_end:
                start_offset_ms = cumulative_ms + (wall_start - seg.started_at).total_seconds() * 1000
            if end_offset_ms is None and seg.started_at <= wall_end <= seg_end:
                end_offset_ms = cumulative_ms + (wall_end - seg.started_at).total_seconds() * 1000

            cumulative_ms += duration_ms

        if start_offset_ms is None:
            return fallback
        if end_offset_ms is None:
            # wall_end wykracza poza to, co dotąd nagrane (np. post-roll
            # eventu jeszcze się nie "wydarzył") — przytnij do końca
            # aktualnej, skumulowanej osi zamiast failować.
            end_offset_ms = cumulative_ms

        edl_path = os.path.join(_edl_dir(), f"camera_{recorder_camera_id}_game_{game_event.game_id}.edl")
        with open(edl_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")

        return {
            'video_path': edl_path,
            'replay_start_time': int(start_offset_ms),
            'replay_end_time': int(end_offset_ms),
        }
    except Exception as e:
        current_app.logger.error(f"build_replay_context failed for event_camera {event_camera.id}: {e}")
        return fallback
