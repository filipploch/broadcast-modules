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