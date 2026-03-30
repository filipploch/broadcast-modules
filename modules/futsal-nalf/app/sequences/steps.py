# app/sequences/steps.py

def obs_mute(input_name: str, muted: bool, delay_ms: int = 0) -> dict:
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


def set_replay_start_time(start_time: int, delay_ms: int = 0, input_name: str="Replay"):
    return {
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

def show_source(scene_name:str="OUTPUT", source_id:int=6, is_visible:bool=True, delay_ms: int = 0):
    _request = {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "SetSceneItemEnabled",
            "requestData": {
                "sceneName": scene_name,
                "sceneItemId": source_id,
                "sceneItemEnabled": is_visible
            }
            }
        ,"delay_ms": delay_ms
    }
    print(f'request: {_request}')
    return _request

def show_transition(delay_ms: int = 0):
    return {
        "target": "stream-overlay",
        "action": "show_transition",
        "payload": {},
        "delay_ms": delay_ms
    }

def move_source(_index, scene_name:str="OUTPUT", source_id:int=7, delay_ms: int = 0):
    return {
        "target": "obs-ws-plugin",
        "action": "obs_command",
        "payload": {
            "requestType": "SetSceneItemIndex",
            "requestData": {
                "sceneName": scene_name,
                "sceneItemId": source_id,
                "sceneItemIndex": _index
            }
        }
        ,"delay_ms": delay_ms
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