"""RecordingLookupManager — zamiana wybranego czasu meczowego (okres +
event_time_delta_s) na plik nagrania i offset w sekundach, dla każdej
kamery, która wtedy nagrywała ten mecz.

Łączy dwa niezależne logi:
  - TimerSample:              elapsed_time_ms głównego timera okresu → czas ścienny
  - CameraRecordingSegment:   który plik nagrywała dana kamera w danym czasie ściennym
"""
from datetime import datetime


class RecordingLookupManager:

    def locate(self, game_id: int, period_id: int, event_time_delta_s: int) -> dict:
        """
        Args:
            game_id:            mecz, którego dotyczy zapytanie
            period_id:          okres (połowa), w którym mieści się event_time_delta_s
            event_time_delta_s: czas meczowy (od początku okresu) w sekundach

        Returns:
            {
                'wall_clock': str|None (ISO, UTC) — obliczony czas ścienny,
                    None jeśli brak jakichkolwiek próbek timera dla tego okresu,
                'cameras': [
                    {'recorder_camera_id': str, 'file_name': str,
                     'file_path': str|None, 'offset_seconds': float},
                    ...  # tylko kamery, które W TYM MOMENCIE faktycznie nagrywały
                ],
            }
        """
        from core.models.base_timer_sample import get_timer_sample_model
        from core.models.base_camera_recording_segment import get_camera_recording_segment_model

        TimerSample = get_timer_sample_model()
        CameraRecordingSegment = get_camera_recording_segment_model()

        wall_clock = TimerSample.wall_clock_for_elapsed(period_id, event_time_delta_s)
        if wall_clock is None:
            return {'wall_clock': None, 'cameras': []}

        cameras = []
        for recorder_camera_id in CameraRecordingSegment.cameras_for_game(game_id):
            segment = CameraRecordingSegment.find_at(recorder_camera_id, game_id, wall_clock)
            if segment is None:
                continue  # ta kamera akurat wtedy nie nagrywała (np. spóźniony start)
            offset_seconds = (wall_clock - segment.started_at).total_seconds()
            cameras.append({
                'recorder_camera_id': recorder_camera_id,
                'file_name': segment.file_name,
                'file_path': segment.file_path,
                'offset_seconds': round(offset_seconds, 1),
            })

        return {
            'wall_clock': wall_clock.isoformat(),
            'cameras': cameras,
        }
