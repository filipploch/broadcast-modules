# core/sequences/steps.py


def obs_mute(input_name: str, muted: bool = True, delay_ms: int = 0) -> dict:
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "SetInputMute",
            "requestData": {"inputName": input_name, "inputMuted": muted}
        },
        "delay_ms": delay_ms
    }


def obs_switch_scene(scene_name: str, delay_ms: int = 0) -> dict:
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "SetCurrentProgramScene",
            "requestData": {"sceneName": scene_name}
        },
        "delay_ms": delay_ms
    }


def overlay_show(container_id: str, delay_ms: int = 0) -> dict:
    return {
        "target":   "broadcast:overlay",
        "action":   "show_container",
        "payload":  {"container_id": container_id},
        "delay_ms": delay_ms
    }


def overlay_hide(container_id: str, delay_ms: int = 0) -> dict:
    return {
        "target":   "broadcast:overlay",
        "action":   "hide_container",
        "payload":  {"container_id": container_id},
        "delay_ms": delay_ms
    }


def overlay_play_animation(container_id: str, animation: str, delay_ms: int = 0) -> dict:
    return {
        "target":   "broadcast:overlay",
        "action":   "play_animation",
        "payload":  {"container_id": container_id, "animation": animation},
        "delay_ms": delay_ms
    }


def set_replay_file(file_path: str, delay_ms: int = 0,
                    input_name: str = "Replay",
                    overlay: bool = False,
                    playback_behavior: str = None) -> dict:
    settings = {
        "loop": False,
        "playlist": [{"hidden": False, "selected": False, "value": file_path}]
    }
    if playback_behavior:
        settings["playback_behavior"] = playback_behavior
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "SetInputSettings",
            "requestData": {
                "inputName":     input_name,
                "inputSettings": settings,
                "overlay":       overlay,
            }
        },
        "delay_ms": delay_ms
    }


def set_replay_start_time(start_time: int, delay_ms: int = 0,
                          input_name: str = "Replay",
                          wait_for_obs_event: str = None,
                          timeout_ms: int = 5000) -> dict:
    step = {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "SetMediaInputCursor",
            "requestData": {
                "inputName":   input_name,
                "mediaCursor": start_time,
            }
        },
        "delay_ms": delay_ms
    }
    if wait_for_obs_event:
        step["wait_for_obs_event"] = wait_for_obs_event
        step["timeout_ms"] = timeout_ms
    return step


def start_replay(delay_ms: int = 0, input_name: str = "Replay") -> dict:
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "TriggerMediaInputAction",
            "requestData": {
                "inputName":   input_name,
                "mediaAction": "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY",
            }
        },
        "delay_ms": delay_ms
    }


def restart_replay(delay_ms: int = 0, input_name: str = "Replay") -> dict:
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "TriggerMediaInputAction",
            "requestData": {
                "inputName":   input_name,
                "mediaAction": "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
            }
        },
        "delay_ms": delay_ms
    }


def pause_replay(delay_ms: int = 0, input_name: str = "Replay") -> dict:
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "TriggerMediaInputAction",
            "requestData": {
                "inputName":   input_name,
                "mediaAction": "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE",
            }
        },
        "delay_ms": delay_ms
    }


def show_source(scene_name: str = "OUTPUT", source_name: str = "Replay",
                is_visible: bool = True, delay_ms: int = 0) -> dict:
    """
    Pokazuje lub ukrywa źródło w scenie OBS.
    ID źródła rozwiązywane w runtime przez obs-ws-plugin.
    """
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command_by_name",
        "payload": {
            "requestType": "SetSceneItemEnabled",
            "sceneName":   scene_name,
            "sourceName":  source_name,
            "requestData": {
                "sceneName":        scene_name,
                "sceneItemEnabled": is_visible,
            }
        },
        "delay_ms": delay_ms
    }


def watch_media_cursor(scene_name: str = "OUTPUT",
                       source_name: str = "Replay",
                       poll_interval_ms: int = 250,
                       min_cursor_ms: int = 5000,
                       visible_duration_ms: int = 10000,
                       delay_ms = 0,
                       timeout_ms: int = 30000) -> dict:
    """
    Krok złożony obsługiwany lokalnie przez SequenceManager — nie wysyłany do huba.

    Polluje GetMediaInputStatus co poll_interval_ms aż mediaCursor >= min_cursor_ms,
    wtedy pokazuje źródło i po visible_duration_ms ukrywa je.
    Jeśli timeout_ms minie bez sukcesu — przerywa cicho.
    """
    return {
        "action":  "watch_media_cursor",
        "payload": {
            "scene_name":          scene_name,
            "source_name":         source_name,
            "poll_interval_ms":    poll_interval_ms,
            "min_cursor_ms":       min_cursor_ms,
            "visible_duration_ms": visible_duration_ms,
            "timeout_ms":          timeout_ms,
        },
        "delay_ms": delay_ms
    }


def move_source(index: int, scene_name: str = "OUTPUT",
                source_name: str = "Replay", delay_ms: int = 0) -> dict:
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command_by_name",
        "payload": {
            "requestType": "SetSceneItemIndex",
            "sceneName":   scene_name,
            "sourceName":  source_name,
            "requestData": {
                "sceneName":      scene_name,
                "sceneItemIndex": index,
            }
        },
        "delay_ms": delay_ms
    }


def show_transition(delay_ms: int = 0) -> dict:
    return {
        "target":   "stream-overlay",
        "action":   "show_transition",
        "payload":  {},
        "delay_ms": delay_ms
    }


def start_recording(cameras: dict = None, delay_ms: int = 0) -> dict:
    import datetime
    from core.models.base_game_camera import HDMI_TO_DEVICE
    from core.models.base_settings import get_settings_model
    _cameras = cameras if cameras is not None else {d: False for d in HDMI_TO_DEVICE.values()}

    # match_id/period_id — meczu/okresu aktualnie ustawionego jako transmitowany
    # w chwili odpalenia komendy. Plugin wpisuje je do meta pliku i odsyła z
    # powrotem w recording_started, żeby dało się zapisać camera_recording_segment
    # przypisany do właściwego meczu/okresu (patrz recorder_manager.on_recording_started).
    Settings = get_settings_model()
    settings = Settings.get_settings()
    match_id  = str(settings.current_game_id) if settings.current_game_id else None
    period_id = str(settings.current_period_id) if settings.current_period_id else None

    return {
        "target": "broadcast",
        "action": "recording_command",
        "payload": {
            'requestType': 'StartRecord',
            'requestData': {},
            'request_id':  f'my-unique-id-{datetime.datetime.now()}',
            'cameras': _cameras,
            'match_id':  match_id,
            'period_id': period_id,
        },
        "delay_ms": delay_ms
    }


def stop_recording(cameras: dict = None, delay_ms: int = 0) -> dict:
    import datetime
    from core.models.base_game_camera import HDMI_TO_DEVICE
    _cameras = cameras if cameras is not None else {d: False for d in HDMI_TO_DEVICE.values()}
    return {
        "target": "broadcast",
        "action": "recording_command",
        "payload": {
            'requestType': 'StopRecord',
            'requestData': {},
            'request_id':  f'my-unique-id-{datetime.datetime.now()}',
            'cameras': _cameras,
        },
        "delay_ms": delay_ms
    }


def start_stream(delay_ms: int = 0) -> dict:
    import datetime
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            'requestType': 'StartStream',
            'requestData': {},
            'request_id':  f'my-unique-id-{datetime.datetime.now()}',
        },
        "delay_ms": delay_ms
    }


def stop_stream(delay_ms: int = 0) -> dict:
    import datetime
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            'requestType': 'StopStream',
            'requestData': {},
            'request_id':  f'my-unique-id-{datetime.datetime.now()}',
        },
        "delay_ms": delay_ms
    }


def show_overlay_container(_data, delay_ms: int = 0) -> dict:
    from core.utils.socketio_events_utils import generate_show_overlay_data
    data = generate_show_overlay_data(_data)
    return {
        "target":   "stream-overlay",
        "action":   "show_overlay_container",
        "payload":  data,
        "delay_ms": delay_ms
    }
