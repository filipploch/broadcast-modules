# app/sequences/sequences.py
from app.sequences.steps import obs_mute, obs_switch_scene, overlay_show, overlay_play_animation

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

SEQUENCES = {
    "halftime_start": [
        overlay_show("game-screen-container"),
        obs_switch_scene("PRZERWA", delay_ms=200),
    ]
}

# Sekwencje dynamiczne - wywoływane z kontekstem
DYNAMIC_SEQUENCES = {
    "goal": goal_sequence,
}