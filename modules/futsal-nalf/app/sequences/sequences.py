# app/sequences/sequences.py
from app.sequences.steps import obs_mute, obs_switch_scene, overlay_show, overlay_play_animation, set_replay_file,\
    set_replay_start_time, start_replay, show_transition, show_source, start_recording, stop_recording,\
    start_stream, stop_stream, show_overlay_container

def goal_sequence(team: str, player_name: str) -> list:
    return [
        overlay_play_animation(f"goal-banner-{team}", "celebrate"),
        overlay_show("player-info", delay_ms=200),
        # payload może zawierać dynamiczne dane
        {
            "target": "broadcast:overlay_receiver",
            "action": "show_player_info",
            "payload": {"player": player_name, "team": team},
            "delay_ms": 200
        }
    ]


def replay_sequence(context):
    _file_path = context['video_path']
    _replay_start_time = context['replay_start_time']
    _replay_end_time = context['replay_end_time']
    _replay_duration = _replay_end_time - _replay_start_time
    return [
        set_replay_file(_file_path),                                      # t=0
        start_replay(delay_ms=200),                                                    # t=0
        set_replay_start_time(_replay_start_time, delay_ms=400),          # t=500
        # show_transition(delay_ms=600),                                     # t=600
        show_source(delay_ms=600),                                         # t=700
        set_replay_start_time(_replay_start_time, delay_ms=700),          # t=500
        # show_transition(delay_ms=1620 + _replay_duration),                  # t=700+duration
        show_source(is_visible=False, delay_ms=700 + _replay_duration)  # t=700+duration+700
    ]

def start_live_sequence(context):
    return [
        obs_mute('Mic1', delay_ms=0),
        obs_mute('Mic2', delay_ms=50),
        show_source('AUDIO_SOURCES', 2, False, delay_ms=100),
        show_source('AUDIO_SOURCES', 3, False, delay_ms=150),
        show_source('OUTPUT', 3, False, delay_ms=200),
        obs_switch_scene('EMPTY', delay_ms=250),
        # start_stream(delay_ms=0),
        start_recording(delay_ms=500),
        show_source('AUDIO_SOURCES', 2, True, delay_ms=550),
        obs_switch_scene('OUTPUT', delay_ms=600),
        show_source('OUTPUT', 3, True, delay_ms=650),
        show_overlay_container({'container_id': 'start-container'}, delay_ms=1000),
        obs_mute('Mic1', muted=False, delay_ms=2000),
        obs_mute('Mic2', muted=False, delay_ms=2050),
    ]

def end_live_sequence(context):
    return [
        show_source('END_SCREEN', 2, False, delay_ms=0),
        obs_mute('Mic1', delay_ms=50),
        obs_mute('Mic2', delay_ms=100),
        show_source('AUDIO_SOURCES', 2, False, delay_ms=150),
        show_source('AUDIO_SOURCES', 3, False, delay_ms=200),
        show_source('END_SCREEN', 2, True, delay_ms=250),
        obs_switch_scene('END_SCREEN', delay_ms=300),
        stop_recording(delay_ms=10500),
        # stop_stream(delay_ms=11000),
    ]

def show_game_scene(context):
    return [
        show_source('AUDIO_SOURCES', 2, False, delay_ms=100),
        show_source('AUDIO_SOURCES', 3, False, delay_ms=150),
        obs_switch_scene('OUTPUT', delay_ms=200),
        show_source('OUTPUT', 3, True, delay_ms=250),
        show_overlay_container({'container_id': 'game-container'}, delay_ms=500),
    ]

def show_break_scene(context):
    return [
        show_source('AUDIO_SOURCES', 2, False, delay_ms=100),
        show_source('AUDIO_SOURCES', 3, True, delay_ms=150),
        obs_switch_scene('OUTPUT', delay_ms=200),
        show_source('OUTPUT', 3, True, delay_ms=250),
        show_overlay_container({'container_id': 'break-container'}, delay_ms=500),
    ]

SEQUENCES = {
    "halftime_start": [
        overlay_show("game-container"),
        obs_switch_scene("PRZERWA", delay_ms=200),
    ]
}

# Sekwencje dynamiczne - wywoływane z kontekstem
DYNAMIC_SEQUENCES = {
    "goal": goal_sequence,
    "replay": replay_sequence,
    "start_live": start_live_sequence,
    "end_live": end_live_sequence,
    "show_game_scene": show_game_scene,
    "show_break_scene": show_break_scene,
}