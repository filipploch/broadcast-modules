# app/sequences/sequences.py
from core.sequences.steps import obs_mute, obs_switch_scene, overlay_show, overlay_play_animation, set_replay_file,\
    set_replay_start_time, start_replay, pause_replay, show_transition, show_source, start_recording, stop_recording,\
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
    _file_path         = context['video_path']
    _replay_start_time = context['replay_start_time']
    _replay_end_time   = context['replay_end_time']
    _replay_duration   = _replay_end_time - _replay_start_time

    # Wybór eventu do synchronizacji SetMediaInputCursor:
    #
    # MediaInputPlaybackStarted — emitowany przy każdym starcie odtwarzania,
    # również przy resecie źródła przez SetInputSettings (stop_restart).
    # Dlatego nie nadaje się jako trigger — możemy złapać fałszywy event
    # przed faktycznym PLAY.
    #
    # MediaInputActionTriggered — emitowany WYŁĄCZNIE w odpowiedzi na
    # TriggerMediaInputAction. Nie jest emitowany przy autostarcie z
    # SetInputSettings. Jednoznacznie identyfikuje wykonanie naszego PLAY.
    # Po tym evencie źródło jest w trakcie przechodzenia do PLAYING —
    # SetMediaInputCursor wysłany natychmiast po nim zostanie przyjęty.
    #
    # Listener jest rejestrowany na starcie sekwencji (przed SetInputSettings),
    # więc nawet gdyby OBS emitował MediaInputActionTriggered z innego powodu,
    # filtr arrived_at > registered_at go odrzuci.

    return [
        # t=0 — załaduj nowy plik; OBS resetuje źródło do STOPPED
        set_replay_file(_file_path),

        # t=600 — pokaż źródło "Replay" w scenie "OUTPUT"
        # Nazwa źródła zamiast hardkodowanego ID — ID rozwiązywane przez ObsWsManager
        show_source(scene_name="OUTPUT", source_name="Replay", delay_ms=600),

        # t=800 — wyślij PLAY → OBS emituje MediaInputActionTriggered
        start_replay(delay_ms=800),

        # eventowy — czeka na MediaInputActionTriggered (tylko po TriggerMediaInputAction)
        # arrived_at > registered_at gwarantuje że nie złapiemy eventu sprzed PLAY
        set_replay_start_time(_replay_start_time,
                              wait_for_obs_event='MediaInputActionTriggered',
                              timeout_ms=5000),

        # t=800+duration — ukryj źródło po zakończeniu powtórki
        show_source(scene_name="OUTPUT", source_name="Replay",
                    is_visible=False, delay_ms=800 + _replay_duration),
    ]

# ---------------------------------------------------------------------------
# Uwaga: sekwencje poniżej używają jeszcze show_source z nazwami źródeł.
# Zamień numeryczne source_id (2, 3, ...) na rzeczywiste nazwy źródeł
# ze swojej struktury scen OBS, np.:
#   show_source('AUDIO_SOURCES', 2, False)  →  show_source('AUDIO_SOURCES', source_name='Lector', is_visible=False)
# Aktualna mapa scen jest dostępna w logach przy starcie obs-ws-plugin
# lub przez API: /api/obs/scene-map
# ---------------------------------------------------------------------------

def start_live_sequence(context):
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
        obs_switch_scene('OUTPUT', delay_ms=600),
        show_source('OUTPUT', source_name='Overlay', is_visible=True, delay_ms=650),
        show_overlay_container({'container_id': 'start-container'}, delay_ms=1000),
        obs_mute('Mic1', muted=False, delay_ms=2000),
        obs_mute('Mic2', muted=False, delay_ms=2050),
    ]

def end_live_sequence(context):
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

def show_game_scene(context):
    return [
        show_source('AUDIO_SOURCES', source_name='music_start', is_visible=False, delay_ms=100),
        show_source('AUDIO_SOURCES', source_name='music_break', is_visible=False, delay_ms=150),
        obs_switch_scene('OUTPUT', delay_ms=200),
        show_source('OUTPUT', source_name='Overlay', is_visible=True, delay_ms=250),
        show_overlay_container({'container_id': 'game-container'}, delay_ms=500),
    ]

def show_break_scene(context):
    return [
        show_source('AUDIO_SOURCES', source_name='music_start', is_visible=False, delay_ms=100),
        show_source('AUDIO_SOURCES', source_name='music_break', is_visible=True, delay_ms=150),
        obs_switch_scene('OUTPUT', delay_ms=200),
        show_source('OUTPUT', source_name='Overlay', is_visible=True, delay_ms=250),
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