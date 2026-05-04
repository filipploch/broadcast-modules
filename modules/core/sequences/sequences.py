# core/sequences/sequences.py
from core.sequences.steps import (
    obs_mute, obs_switch_scene, overlay_show, overlay_play_animation,
    set_replay_file, restart_replay, set_replay_start_time,
    show_source, watch_media_cursor,
    start_recording, stop_recording, start_stream, stop_stream,
    show_overlay_container,
)
from flask import current_app
import json
import os


def _get_replay_transition_lead_ms(default=700):
    """
    Czyta opóźnienie transition dla Replay z konfiguracji aplikacji albo
    z plugins/replay-plugin/config.json. Ta sama wartość decyduje o tym,
    jak wcześnie OBS ma ukryć źródło Replay przed pauzą mpv.
    """
    value = current_app.config.get('REPLAY_TRANSITION_LEAD_MS')
    if value is not None:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            current_app.logger.warning(
                f"Niepoprawne REPLAY_TRANSITION_LEAD_MS={value!r}; używam {default}ms"
            )

    config_path = current_app.config.get(
        'REPLAY_PLUGIN_CONFIG',
        os.path.abspath(os.path.join(current_app.root_path, '..', 'plugins', 'replay-plugin', 'config.json'))
    )
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return max(0, int(data.get('transition_lead_ms', default)))
    except Exception as exc:
        current_app.logger.warning(
            f"Nie mogę odczytać transition_lead_ms z {config_path}: {exc}; używam {default}ms"
        )
        return default


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
      t=transition_lead_ms → SetSceneItemEnabled(Replay, true)
                  transition_lead_ms jest czytane z config.json replay-plugin
                  i synchronizuje pokazanie/ukrycie źródła Replay z mpv

      [replay trwa — replay-plugin monitoruje AB-loop]

      Po odebraniu 'replay_done' z replay-plugin:
      t+0ms     → SetSceneItemEnabled(Replay, false)
                  replay-plugin pauzuje mpv dopiero po transition_lead_ms, więc
                  OBS ukrywa źródło wcześniej niż faktyczny koniec powtórki.

    Zakończenie powtórki NIE jest hardkodowane czasowo — sekwencja czeka
    na sygnał 'replay_done' od replay-plugin (wait_for_hub_message).
    Timeout jest tylko długim zabezpieczeniem awaryjnym konfigurowanym przez
    REPLAY_WAIT_TIMEOUT_MS.
    """
    scene_name  = current_app.config.get('REPLAY_SCENE',  'OUTPUT')
    source_name = current_app.config.get('REPLAY_SOURCE', 'Replay')

    replay_duration_ms = context.get('replay_end_time', 0) - context.get('replay_start_time', 0)
    speed              = context.get('speed', current_app.config.get('REPLAY_DEFAULT_SPEED', 0.9))
    # Szacowany czas trwania powtórki z uwzględnieniem prędkości
    # Używany tylko jako sugestia dla replay-plugin — zakończenie triggeruje replay_done
    estimated_duration_ms = int(replay_duration_ms / speed) if speed > 0 else replay_duration_ms

    wait_timeout_ms = current_app.config.get('REPLAY_WAIT_TIMEOUT_MS', 600_000)
    transition_lead_ms = _get_replay_transition_lead_ms()

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

        # 2. Po czasie z config.json włącz widoczność Replay w OBS.
        #    Ten sam lead jest używany przy końcu: OBS ukrywa źródło po replay_done,
        #    a replay-plugin pauzuje mpv dopiero po transition_lead_ms.
        show_source(scene_name, source_name, is_visible=True, delay_ms=transition_lead_ms),

        # 3. Czekaj na sygnał zakończenia od replay-plugin
        #    replay-plugin wyśle 'replay_done' po czasie z DB albo po ręcznym end_replay.
        #    Długi timeout jest tylko bezpiecznikiem awaryjnym, żeby ręczna powtórka
        #    nie została ukryta po krótkim czasie bez sygnału użytkownika.
        {
            'wait_for_hub_message': 'replay_done',
            'timeout_ms':           wait_timeout_ms,
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
