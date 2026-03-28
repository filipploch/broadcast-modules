# app/sequences/sequences.py
from app.sequences.steps import obs_mute, obs_switch_scene, overlay_show, overlay_play_animation, set_replay_file,\
    set_replay_start_time, start_replay, show_transition, show_source

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
        start_replay(),                                                    # t=0
        set_replay_start_time(_replay_start_time, delay_ms=500),          # t=500
        show_transition(delay_ms=600),                                     # t=600
        show_source(delay_ms=1620),                                         # t=700
        show_transition(delay_ms=1620 + _replay_duration),                  # t=700+duration
        show_source(is_visible=False, delay_ms=1620 + _replay_duration + 1000)  # t=700+duration+700
    ]

SEQUENCES = {
    "halftime_start": [
        overlay_show("game-screen-container"),
        obs_switch_scene("PRZERWA", delay_ms=200),
    ]
}

# Sekwencje dynamiczne - wywoływane z kontekstem
DYNAMIC_SEQUENCES = {
    "goal": goal_sequence,
    "replay": replay_sequence,
}