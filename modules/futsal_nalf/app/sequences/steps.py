# app/sequences/steps.py

def obs_mute(input_name: str, muted: bool=True, delay_ms: int = 0) -> dict:
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
        "target": "broadcast:overlay",
        "action": "show_container",
        "payload": {"container_id": container_id},
        "delay_ms": delay_ms
    }

def overlay_hide(container_id: str, delay_ms: int = 0) -> dict:
    return {
        "target": "broadcast:overlay",
        "action": "hide_container",
        "payload": {"container_id": container_id},
        "delay_ms": delay_ms
    }

def overlay_play_animation(container_id: str, animation: str, delay_ms: int = 0) -> dict:
    return {
        "target": "broadcast:overlay",
        "action": "play_animation",
        "payload": {"container_id": container_id, "animation": animation},
        "delay_ms": delay_ms
    }

def set_replay_file(file_path, delay_ms: int = 0, input_name="Replay"):
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType":"SetInputSettings",
            "requestData":{
                "inputName": "Replay",
                "inputSettings": {
                "loop": False,
                "playback_behavior": "stop_restart",
                "playlist": [
                    {
                    "hidden": False,
                    "selected": False,
                    "uuid": "a0f86de7-e18c-4768-929b-d111820145ea",
                    "value": file_path
                    }
                ]
                },
                "overlay": True
            }
            },
        "delay_ms": delay_ms
    }


def set_replay_start_time(start_time: int, delay_ms: int = 0, input_name: str = "Replay",
                          wait_for_obs_event: str = None,
                          timeout_ms: int = 5000):
    step = {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "SetMediaInputCursor",
            "requestData": {
                "inputName": input_name,
                "mediaCursor": start_time
                }
            },
        "delay_ms": delay_ms
    }
    if wait_for_obs_event:
        step["wait_for_obs_event"] = wait_for_obs_event
        step["timeout_ms"] = timeout_ms
    return step

def start_replay(delay_ms: int = 0, input_name: str="Replay"):
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "TriggerMediaInputAction",
            "requestData": {
                "inputName": input_name,
                "mediaAction": "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY"
                }
            },
        "delay_ms": delay_ms
    }

def pause_replay(delay_ms: int = 0, input_name="Replay"):
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "TriggerMediaInputAction",
            "requestData": {
                "inputName": input_name,
                "mediaAction": "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE"
                }
            },
        "delay_ms": delay_ms
    }

def show_transition(delay_ms: int = 0):
    return {
        "target": "stream-overlay",
        "action": "show_transition",
        "payload": {},
        "delay_ms": delay_ms
    }


def show_source(scene_name: str = "OUTPUT", source_name: str = "Replay",
                is_visible: bool = True, delay_ms: int = 0):
    """
    Pokazuje lub ukrywa źródło w scenie OBS.

    Używa nazwy źródła zamiast numerycznego sceneItemId —
    ID jest rozwiązywane w runtime przez ObsWsManager.get_scene_item_id().
    Nie wymaga aktualizacji kodu po zmianie struktury scen w OBS.
    """
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command_by_name",   # nowy action — plugin rozwiązuje ID
        "payload": {
            "requestType": "SetSceneItemEnabled",
            "sceneName": scene_name,
            "sourceName": source_name,
            "requestData": {
                "sceneName": scene_name,
                "sceneItemEnabled": is_visible,
                # sceneItemId zostanie wstrzyknięte przez ObsWsManager przed wysłaniem
            }
        },
        "delay_ms": delay_ms
    }


def move_source(index, scene_name: str = "OUTPUT", source_name: str = "Replay",
                delay_ms: int = 0):
    """
    Zmienia kolejność źródła (z-index) w scenie OBS.

    Używa nazwy źródła zamiast numerycznego sceneItemId.
    """
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command_by_name",
        "payload": {
            "requestType": "SetSceneItemIndex",
            "sceneName": scene_name,
            "sourceName": source_name,
            "requestData": {
                "sceneName": scene_name,
                "sceneItemIndex": index,
                # sceneItemId zostanie wstrzyknięte przez ObsWsManager przed wysłaniem
            }
        },
        "delay_ms": delay_ms
    }

def start_recording(cameras: dict = None, delay_ms: int = 0) -> dict:
    import datetime
    return {
        "target": "broadcast",
        "action": "recording_command",
        "payload": {
            'requestType': 'StartRecord',
            'requestData': {},
            'request_id': f'my-unique-id-{datetime.datetime.now()}',
            'cameras':{'camera1': True,
                       'camera2': False,
                       'camera3': False,
                       'camera4': False}},
        "delay_ms": delay_ms
    }

def stop_recording(cameras: dict = None, delay_ms: int = 0) -> dict:
    import datetime
    return {
        "target": "broadcast",
        "action": "recording_command",
        "payload": {
            'requestType': 'StopRecord',
            'requestData': {},
            'request_id': f'my-unique-id-{datetime.datetime.now()}',
            'cameras':{'camera1': True,
                       'camera2': False,
                       'camera3': False,
                       'camera4': False}},
        "delay_ms": delay_ms
    }

def start_stream(delay_ms: int=0) -> dict:
    import datetime
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            'requestType': 'StartStream',
            'requestData': {},
            'request_id': f'my-unique-id-{datetime.datetime.now()}',
            },
        "delay_ms": delay_ms
    }

def stop_stream(delay_ms: int=0) -> dict:
    import datetime
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            'requestType': 'StopStream',
            'requestData': {},
            'request_id': f'my-unique-id-{datetime.datetime.now()}',
            },
        "delay_ms": delay_ms
    }

def show_overlay_container(_data, delay_ms: int=0) -> dict:
    from app.utils.socketio_events_utils import generate_show_overlay_data
    data = generate_show_overlay_data(_data)
    return {
        "target": "stream-overlay",
        "action": "show_overlay_container",
        "payload": data,
        "delay_ms": delay_ms
    }

# def _get_scene_item_list(scene_name="OUTPUT"):
#     return {
#         "target": "obs-ws-plugin",
#         "action": "obs_command",
#         "payload": 
#             {"requestType":"GetSceneItemList",
#             "requestData":
#                 {"sceneName":"PUSTA"}
#             }
#     }

'''
{"requestType":"GetSceneItemList","requestData":{"sceneName":"PUSTA"}}
'''