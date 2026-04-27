# core/sequences/sequences.py
from core.sequences.steps import (
    obs_mute, obs_switch_scene, overlay_show, overlay_play_animation,
    set_replay_file, restart_replay, set_replay_start_time,
    show_source, watch_media_cursor,
    start_recording, stop_recording, start_stream, stop_stream,
    show_overlay_container,
)
from flask import current_app


def goal_sequence(team: str, player_name: str) -> list:
    return [
        overlay_play_animation(f"goal-banner-{team}", "celebrate"),
        overlay_show("player-info", delay_ms=200),
        {
            "target":   "broadcast:overlay_receiver",
            "action":   "show_player_info",
            "payload":  {"player": player_name, "team": team},
            "delay_ms": 200
        }
    ]


def replay_sequence(context) -> list:
    _file_path         = context['video_path']
    _replay_start_time = context['replay_start_time']

    overlay           = current_app.config.get('REPLAY_OVERLAY', False)
    playback_behavior = current_app.config.get('REPLAY_PLAYBACK_BEHAVIOR', None)

    return [
        # 1. Uruchom polling cursora w tle — czeka aż cursor >= 2000ms,
        #    wtedy pokazuje scenę Replay i po 10s ją ukrywa
        watch_media_cursor(scene_name="OUTPUT", source_name="Replay",
                           delay_ms=200),

        # 2. Załaduj plik
        set_replay_file(_file_path,
                        overlay=overlay, playback_behavior="pause_unpause"),

        # 3. RESTART — wymusza przejście do PLAYING nawet ze stanu STOPPED
        restart_replay(delay_ms=100),

        # 4. Seek do właściwej pozycji — OBS zaakceptuje bo źródło gra
        set_replay_start_time(_replay_start_time, delay_ms=700),
    ]


def start_live_sequence(context) -> list:
    return [
        obs_mute('Mic1', delay_ms=0),
        obs_mute('Mic2', delay_ms=50),
        show_source('AUDIO_SOURCES', source_name='music_start', is_visible=False, delay_ms=100),
        show_source('AUDIO_SOURCES', source_name='music_break', is_visible=False, delay_ms=150),
        show_source('OUTPUT', source_name='Overlay', is_visible=False, delay_ms=200),
        obs_switch_scene('EMPTY', delay_ms=250),
        start_stream(delay_ms=300),
        start_recording(delay_ms=500),
        show_source('AUDIO_SOURCES', source_name='music_start', is_visible=True, delay_ms=550),
        obs_switch_scene('STREAM', delay_ms=600),
        show_source('OUTPUT', source_name='Overlay', is_visible=True, delay_ms=650),
        show_overlay_container({'container_id': 'start-container'}, delay_ms=1000),
        obs_mute('Mic1', muted=False, delay_ms=2000),
        obs_mute('Mic2', muted=False, delay_ms=2050),
    ]


def end_live_sequence(context) -> list:
    return [
        show_source('END_SCREEN', source_name='outro-sociale', is_visible=False, delay_ms=0),
        obs_mute('Mic1', delay_ms=50),
        obs_mute('Mic2', delay_ms=100),
        show_source('AUDIO_SOURCES', source_name='music_start', is_visible=False, delay_ms=150),
        show_source('AUDIO_SOURCES', source_name='music_break', is_visible=False, delay_ms=200),
        show_source('END_SCREEN', source_name='outro-sociale', is_visible=True, delay_ms=250),
        obs_switch_scene('END_SCREEN', delay_ms=300),
        stop_recording(delay_ms=10500),
        stop_stream(delay_ms=11000),
    ]


def show_game_scene(context) -> list:
    return [
        show_source('AUDIO_SOURCES', source_name='music_start', is_visible=False, delay_ms=100),
        show_source('AUDIO_SOURCES', source_name='music_break', is_visible=False, delay_ms=150),
        obs_switch_scene('STREAM', delay_ms=200),
        show_source('OUTPUT', source_name='Overlay', is_visible=True, delay_ms=250),
        show_overlay_container({'container_id': 'game-container'}, delay_ms=500),
    ]


def show_break_scene(context) -> list:
    return [
        show_source('AUDIO_SOURCES', source_name='music_start', is_visible=False, delay_ms=100),
        show_source('AUDIO_SOURCES', source_name='music_break', is_visible=True, delay_ms=150),
        obs_switch_scene('STREAM', delay_ms=200),
        show_source('OUTPUT', source_name='Overlay', is_visible=True, delay_ms=250),
        show_overlay_container({'container_id': 'break-container'}, delay_ms=500),
    ]


SEQUENCES = {
    "halftime_start": [
        overlay_show("game-container"),
        obs_switch_scene("PRZERWA", delay_ms=200),
    ]
}

DYNAMIC_SEQUENCES = {
    "goal":             goal_sequence,
    "replay":           replay_sequence,
    "start_live":       start_live_sequence,
    "end_live":         end_live_sequence,
    "show_game_scene":  show_game_scene,
    "show_break_scene": show_break_scene,
}
