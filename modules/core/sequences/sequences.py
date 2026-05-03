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
    """
    Sekwencja powtórki z replay-plugin (mpv) i transition OBS.

    Przepływ:
      t=0ms     → SetSceneItemEnabled(Replay, false) — upewnij się że Replay ukryty
      t=0ms     → replay_play do replay-plugin — mpv ładuje plik, seekuje, czeka na start
      t=700ms   → SetSceneItemEnabled(Replay, true)
                  OBS triggeruje transition (stinger) — transition zasłania przejście
                  mpv zaczyna odtwarzać (synchronizacja z transition)

      [replay trwa — replay-plugin monitoruje AB-loop]

      Po odebraniu 'replay_done' z replay-plugin:
      t+0ms     → SetSceneItemEnabled(Replay, false)
                  OBS triggeruje transition — transition zasłania powrót do live

    Zakończenie powtórki NIE jest hardkodowane czasowo — sekwencja czeka
    na sygnał 'replay_done' od replay-plugin (wait_for_hub_message).
    Timeout 120s jako zabezpieczenie.
    """
    scene_name  = current_app.config.get('REPLAY_SCENE',  'OUTPUT')
    source_name = current_app.config.get('REPLAY_SOURCE', 'Replay')

    replay_duration_ms = context.get('replay_end_time', 0) - context.get('replay_start_time', 0)
    speed              = context.get('speed', current_app.config.get('REPLAY_DEFAULT_SPEED', 0.9))
    # Szacowany czas trwania powtórki z uwzględnieniem prędkości
    # Używany tylko jako sugestia dla replay-plugin — zakończenie triggeruje replay_done
    estimated_duration_ms = int(replay_duration_ms / speed) if speed > 0 else replay_duration_ms

    return [
        # 0. Upewnij się że Replay jest ukryty
        show_source(scene_name, source_name, is_visible=False, delay_ms=0),

        # 1. Wyślij replay_play do replay-plugin
        #    mpv ładuje plik i czeka — odtworzy po otrzymaniu sygnału
        {
            'target':   'replay-plugin',
            'action':   'replay_play',
            'payload':  {
                'video_path':        context.get('video_path'),
                'replay_start_time': context.get('replay_start_time', 0),
                'replay_end_time':   context.get('replay_end_time', 0),
                'speed':             speed,
                'estimated_duration_ms': estimated_duration_ms,
                'scene_name':        scene_name,
                'source_name':       source_name,
            },
            'delay_ms': 0,
        },

        # 2. Po 700ms włącz widoczność Replay w OBS
        #    OBS triggeruje transition (stinger) — zasłania przejście do powtórki
        show_source(scene_name, source_name, is_visible=True, delay_ms=700),

        # 3. Czekaj na sygnał zakończenia od replay-plugin
        #    replay-plugin wyśle 'replay_done' gdy AB-loop się zakończy
        #    on_timeout: wyłącz Replay po 120s jeśli sygnał nie nadejdzie
        {
            'wait_for_hub_message': 'replay_done',
            'timeout_ms':           20_000,
            'target':               'obs-ws-plugin',
            'action':               'obs_command_by_name',
            'payload': {
                'requestType': 'SetSceneItemEnabled',
                'sceneName':   scene_name,
                'sourceName':  source_name,
                'requestData': {
                    'sceneName':        scene_name,
                    'sceneItemEnabled': False,
                },
            },
            'on_timeout': [
                show_source(scene_name, source_name, is_visible=False, delay_ms=0),
            ],
        },
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
