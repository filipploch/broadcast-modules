"""
core.socketio_events.base — wspólne handlery SocketIO dla wszystkich modułów.

Obsługuje: connect/disconnect, timer control, OBS, recorder,
           sekwencje, replay export, scoreboard reverse.

Rejestracja:
    from core.socketio_events import base as core_events
    core_events.register_events(socketio)
"""
from core.managers import session_manager
import logging
from flask import current_app

logger = logging.getLogger(__name__)

def _get_settings():
    from core.models.base_settings import get_settings_model
    return get_settings_model()

def _send_wol_packet(mac_address):
    """Broadcasts a Wake-on-LAN magic packet (6x 0xFF + MAC repeated 16x)
    as a UDP datagram on port 9 — same effect as the usual PowerShell
    one-liner, done natively so it works regardless of what OS main-module
    runs on."""
    import socket as pysocket

    mac_bytes = bytes.fromhex(mac_address.replace(':', '').replace('-', ''))
    magic_packet = b'\xff' * 6 + mac_bytes * 16

    sock = pysocket.socket(pysocket.AF_INET, pysocket.SOCK_DGRAM)
    try:
        sock.setsockopt(pysocket.SOL_SOCKET, pysocket.SO_BROADCAST, 1)
        sock.sendto(magic_packet, ('255.255.255.255', 9))
    finally:
        sock.close()

# Sentinel odróżniający "nie podano" od jawnego None (BRAK) dla team_id w podglądzie edycji.
_TEAM_ID_NOT_SET = object()

def _get_game_event_data(game_event_id, new_event_type_id=None, new_team_id=_TEAM_ID_NOT_SET):
    from core.managers.game_event_manager import GameEventManager
    from core.managers.game_manager import GameManager

    gem        = GameEventManager()
    game_event = gem.get_game_event_by_id(game_event_id)
    game_data  = GameManager().get_game_by_id(game_event.game_id)

    if new_event_type_id:
        game_event.event_id = new_event_type_id
    if new_team_id is not _TEAM_ID_NOT_SET:
        game_event.team_id = new_team_id

    # Zawodnik przypisany do zdarzenia pochodzi z drużyny przeciwnej do team_id
    # dla zdarzeń typu player_from_opponent (bramka samobójcza, obrona).
    team_squad = None
    if game_event.team_id is not None:
        is_home = game_event.team_id == game_data.home_team_id
        if game_event.event and game_event.event.player_from_opponent:
            is_home = not is_home
        team_squad = 'home_team_squad' if is_home else 'away_team_squad'

    return {
        'team_squad':            game_data.to_dict()[team_squad] if team_squad else None,
        'game_event':             game_event.to_dict(),
        'home_team_id':          game_data.home_team_id,
        'away_team_id':          game_data.away_team_id,
        'home_team_short_name':  game_data.home_team.short_name if game_data.home_team else None,
        'away_team_short_name':  game_data.away_team.short_name if game_data.away_team else None,
    }

def register_events(socketio):
    """Rejestruje wspólne handlery SocketIO."""

    @socketio.on('connect')
    def handle_connect():
        from flask_socketio import emit
        logger.info('Client connected')
        socketio.emit('connected', {'status': 'ok'})
        from core.managers import get_servo_manager
        sm = get_servo_manager()
        if sm:
            for head in sm.get_heads():
                if head.get('online'):
                    emit('servo_head_online', {'head_id': head['head_id']})

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('Client disconnected')

    # ── Timer ─────────────────────────────────────────────────────────────────

    @socketio.on('timer_start')
    def handle_timer_start(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.start_timer(timer_id):
            socketio.emit('timer_started', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to start timer: {timer_id}'})

    @socketio.on('timer_pause')
    def handle_timer_pause(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.pause_timer(timer_id):
            socketio.emit('timer_paused', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to pause timer: {timer_id}'})

    @socketio.on('timer_resume')
    def handle_timer_resume(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.resume_timer(timer_id):
            socketio.emit('timer_resumed', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to resume timer: {timer_id}'})

    @socketio.on('timer_reset')
    def handle_timer_reset(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.reset_timer(timer_id):
            socketio.emit('timer_reset', {'timer_id': timer_id})
        else:
            socketio.emit('error', {'message': f'Failed to reset timer: {timer_id}'})

    @socketio.on('timer_remove')
    def handle_timer_remove(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        if tm.remove_timer(timer_id):
            socketio.emit('timer_removed', {'timer_id': timer_id})
            if timer_id and (timer_id.startswith('penalty_home') or
                             timer_id.startswith('penalty_away')):
                from core.models.base_game_timer import get_game_timer_model
                from core.extensions import db
                GameTimer = get_game_timer_model()
                gt = GameTimer.query.filter_by(plugin_timer_id=timer_id).first()
                if gt:
                    game_id = gt.game_id
                    db.session.delete(gt)
                    db.session.commit()
                    tm._broadcast_penalty_state(game_id)
                    penalties = tm._get_penalties_dict(game_id)
                    socketio.emit('reload_penalty_timers', {'penalties': penalties})
        else:
            socketio.emit('error', {'message': f'Failed to remove timer: {timer_id}'})

    @socketio.on('timer_adjust')
    def handle_timer_adjust(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id = data.get('timer_id')
        delta = data.get('delta', 0)
        tm.adjust_time(timer_id, delta)

        # Dla kar: zapisz korektę też w bazie (adjustment_ms), inaczej
        # migawka używana przez derived-variable (overlay + UI) — wyliczana
        # z start_offset_ms/limit_ms/adjustment_ms — nie odzwierciedli ręcznej
        # korekty +/-, mimo że sam plugin ją zastosował.
        if timer_id and (timer_id.startswith('penalty_home') or
                         timer_id.startswith('penalty_away')):
            from core.models.base_game_timer import get_game_timer_model
            from core.extensions import db
            GameTimer = get_game_timer_model()
            gt = GameTimer.query.filter_by(plugin_timer_id=timer_id).first()
            if gt:
                gt.adjustment_ms = (gt.adjustment_ms or 0) + delta
                db.session.commit()
                penalties = tm._get_penalties_dict(gt.game_id)
                socketio.emit('reload_penalty_timers', {'penalties': penalties})
                tm._broadcast_penalty_state(gt.game_id)

    @socketio.on('timer_set_time')
    def handle_timer_set_time(data):
        from flask_socketio import emit
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        timer_id     = data.get('timer_id')
        elapsed_time = data.get('elapsed_time', 0)
        if tm.set_elapsed_time(timer_id, elapsed_time):
            socketio.emit('timer_time_set', {'timer_id': timer_id, 'elapsed_time': elapsed_time},
                 broadcast=True)

    @socketio.on('timers_get_all')
    def handle_timers_get_all(data):
        from core.managers import get_timer_manager
        get_timer_manager().get_all_timers()

    # ── Recording ─────────────────────────────────────────────────────────────

    @socketio.on('get_camera_assignments')
    def handle_get_camera_assignments():
        from flask_socketio import emit
        from core.models.base_game_camera import HDMI_TO_DEVICE
        logger.info('get_camera_assignments received')
        try:
            from core.managers.game_camera_manager import GameCameraManager
            Settings = _get_settings()
            settings = Settings.get_settings()
            logger.info('get_camera_assignments: settings=%s', settings)
            if settings and session_manager.current_game_id():
                cameras = GameCameraManager().get_cameras_dict_for_game(session_manager.current_game_id())
            else:
                cameras = {device: False for device in HDMI_TO_DEVICE.values()}
            logger.info('get_camera_assignments: cameras=%s', cameras)
            emit('camera_assignments', {'cameras': cameras})
        except Exception as e:
            logger.exception('get_camera_assignments error: %s', e)
            emit('camera_assignments', {'cameras': {d: False for d in HDMI_TO_DEVICE.values()}})

    @socketio.on('start_recording')
    def handle_start_recording(data=None):
        from core.managers import get_hub_client
        from core.managers import get_recorder_manager
        from flask_socketio import emit
        hub_client = get_hub_client()
        if hub_client:
            from core.sequences.steps import start_recording
            from core.managers.game_camera_manager import GameCameraManager
            Settings = _get_settings()
            settings = Settings.get_settings()
            cameras = (GameCameraManager().get_cameras_dict_for_game(session_manager.current_game_id())
                       if settings and session_manager.current_game_id() else None)
            step = start_recording(cameras=cameras)
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to': step['target'],
                'type': step['action'],
                'payload': step['payload']
            })

    @socketio.on('stop_recording')
    def handle_stop_recording(data=None):
        from core.managers import get_hub_client
        from flask_socketio import emit
        hub_client = get_hub_client()
        if hub_client:
            from core.sequences.steps import stop_recording
            from core.managers.game_camera_manager import GameCameraManager
            Settings = _get_settings()
            settings = Settings.get_settings()
            cameras = (GameCameraManager().get_cameras_dict_for_game(session_manager.current_game_id())
                       if settings and session_manager.current_game_id() else None)
            step = stop_recording(cameras=cameras)
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to': step['target'],
                'type': step['action'],
                'payload': step['payload']
            })

    @socketio.on('restart_plugin')
    def handle_restart_plugin(data):
        # Przycisk "Uruchom ponownie" przy ikonie pluginu w panelu (index.js).
        from core.managers import get_hub_client
        plugin_id = (data or {}).get('plugin_id')
        hub_client = get_hub_client()
        if not hub_client or not hub_client.request_plugin_restart(plugin_id):
            socketio.emit('plugin_restart_result', {
                'plugin_id': plugin_id, 'ok': False,
                'error': 'Restart nie został wysłany (brak połączenia z HUB-em albo plugin nieobsługiwany)'})

    @socketio.on('wake_recorder_plugin')
    def handle_wake_recorder_plugin():
        # Double-click on #recorder-plugin-icon while it's greyed out (not
        # connected to the hub) — see onRecorderPluginIconDblClick (index.js).
        # The Debian box running recorder-plugin has WOL enabled precisely
        # for this: wake it remotely instead of walking over to it.
        mac = current_app.config.get('RECORDER_PLUGIN_MAC')
        if not mac:
            logger.warning("wake_recorder_plugin: RECORDER_PLUGIN_MAC not configured")
            return
        try:
            _send_wol_packet(mac)
            logger.info(f"📡 Wake-on-LAN packet sent to recorder-plugin host ({mac})")
        except Exception as e:
            logger.error(f"Failed to send WOL packet to {mac}: {e}")

    @socketio.on('shutdown_recorder_plugin')
    def handle_shutdown_recorder_plugin():
        # Double-click on #recorder-plugin-icon while it's healthy/green —
        # see onRecorderPluginIconDblClick (index.js). Replaces doing this
        # by hand over ssh: recorder-plugin stops all recordings/streams
        # cleanly (SIGINT, not a mid-write kill) and then powers the Debian
        # box off itself — see HandleShutdownHost in recorder.go.
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if not hub_client:
            logger.warning("shutdown_recorder_plugin: hub client not available")
            return
        hub_client.send_to_plugin('recorder-plugin', 'shutdown_host', {})
        logger.info("🛑 shutdown_host sent to recorder-plugin")

    @socketio.on('resync_camera_stream_sources')
    def handle_resync_camera_stream_sources():
        # Manual re-trigger for ObsWsManager.sync_camera_stream_sources —
        # normally runs automatically whenever recorder-plugin (re)connects
        # and reports its IP, this is just for troubleshooting without
        # waiting for/forcing a reconnect.
        from core.managers import get_recorder_manager
        get_recorder_manager().resync_camera_stream_sources()

    @socketio.on('get_obs_ws_connection')
    def handle_get_obs_ws_connection():
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if hub_client:
            hub_client.send_to_plugin('obs-ws-plugin', 'obs_command', {
                'requestType': 'GetVersion',
                'requestData': {},
                'request_id': 'get-websocket-connection'
            })

    @socketio.on('get_source_visibility')
    def handle_get_source_visibility(data):
        from flask_socketio import emit
        from core.managers import get_obs_ws_manager
        scene_name  = data.get('scene_name')
        source_name = data.get('source_name')
        obs     = get_obs_ws_manager()
        item_id = obs.get_scene_item_id(scene_name, source_name)
        if item_id is None:
            return
        enabled = obs.get_scene_item_enabled(scene_name, item_id)
        if enabled is not None:
            emit('source_visibility_response', {
                'scene_name':  scene_name,
                'source_name': source_name,
                'enabled':     enabled,
            })

    @socketio.on('toggle_source_visibility')
    def handle_toggle_source_visibility(data):
        from core.managers import get_obs_ws_manager
        from core.extensions import socketio as _sio
        scene_name  = data.get('scene_name')
        source_name = data.get('source_name')
        obs     = get_obs_ws_manager()
        item_id = obs.get_scene_item_id(scene_name, source_name)
        if item_id is None:
            return
        enabled = obs.get_scene_item_enabled(scene_name, item_id)
        if enabled is not None:
            new_enabled = not enabled
            obs.set_scene_item_enabled(scene_name, item_id, new_enabled)
            _sio.emit('source_visibility_changed', {
                'scene_name':  scene_name,
                'source_name': source_name,
                'enabled':     new_enabled,
            })

    # Źródła #camera-controllers-container (.field-games) w scenie "CAMERAS" —
    # dokładnie jedno z nich jest widoczne naraz, więc włączenie jednego
    # oznacza wyłączenie pozostałych czterech. Zobacz camera-controllers.js.
    # CAMERA_CONTROLLER_SOURCES = ('Camera1', 'sCamera1', 'sCamera2', 'sCamera3', 'sCamera4')

    @socketio.on('switch_camera_source')
    def handle_switch_camera_source(data):
        from core.managers import get_obs_ws_manager
        from core.extensions import socketio as _sio
        scene_name  = data.get('scene_name', 'CAMERAS')
        source_name = data.get('source_name')
        source_type = 'OBS_SOURCE_TYPE_INPUT'
        obs = get_obs_ws_manager()
        camera_controller_sources = obs.get_scene_item_list(scene_name, source_type=source_type)
        for _source in camera_controller_sources:
            print(f"Found source in scene '{scene_name}': {_source}")
        if source_name not in [source['sourceName'] for source in camera_controller_sources]:
            return

        
        for source in camera_controller_sources:
            name = source['sourceName']
            item_id = obs.get_scene_item_id(scene_name, name)
            print(f"Switching source: {name}, item_id: {item_id}, target: {source_name}")
            if item_id is None:
                continue
            if name == source_name:
                obs.set_scene_item_enabled(scene_name, item_id, True)
            else:
                obs.set_scene_item_enabled(scene_name, item_id, False)

        _sio.emit('camera_source_switched', {
            'scene_name':  scene_name,
            'source_name': source_name,
        })

    @socketio.on('refresh_overlay_and_switch_scene')
    def handle_refresh_overlay_and_switch_scene():
        from core.managers import get_obs_ws_manager
        obs = get_obs_ws_manager()
        obs.refresh_browser_source('Overlay')
        obs.set_current_program_scene('STREAM')

    @socketio.on('get_obs_record_status')
    def handle_get_obs_record_status():
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if hub_client:
            hub_client.send_to_plugin('obs-ws-plugin', 'obs_command', {
                'requestType': 'GetRecordStatus',
                'requestData': {},
                'request_id': 'ui-obs-record-status',
            })

    @socketio.on('get_obs_stream_status')
    def handle_get_obs_stream_status():
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if hub_client:
            hub_client.send_to_plugin('obs-ws-plugin', 'obs_command', {
                'requestType': 'GetStreamStatus',
                'requestData': {},
                'request_id': 'ui-obs-stream-status',
            })

    @socketio.on('get_camera_recording_status')
    def handle_get_camera_recording_status():
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if hub_client:
            hub_client.send_to_plugin('recorder-plugin', 'recording_status', {})

    @socketio.on('get_camera_source_status')
    def handle_get_camera_source_status():
        # Companion to handle_switch_camera_source above: that one only fires
        # camera_source_switched when a switch actually happens, so a client
        # that (re)loads the panel without ever switching a camera itself
        # never learns which of the 5 CAMERA_CONTROLLER_SOURCES is actually
        # live right now — see camera-controllers.js, whose "M" button starts
        # with is-active hard-coded in the Jinja template as a fallback, same
        # disabled-buttons bug this mirrors for get_camera_recording_status.
        from core.managers import get_obs_ws_manager
        from core.extensions import socketio as _sio
        scene_name = 'CAMERAS'
        source_type = 'OBS_SOURCE_TYPE_INPUT'
        obs = get_obs_ws_manager()
        camera_controller_sources = obs.get_scene_item_list(scene_name, source_type=source_type)
        active_source = next(
            (source['sourceName'] for source in camera_controller_sources if source.get('sceneItemEnabled')),
            None,
        )
        if active_source is None:
            return
        _sio.emit('camera_source_switched', {
            'scene_name':  scene_name,
            'source_name': active_source,
        })

    # ── Filters ───────────────────────────────────────────────────────────────

    @socketio.on('enable_scene_filter')
    def handle_enable_scene_filter(data):
        from core.managers import get_obs_ws_manager
        obs_ws_manager = get_obs_ws_manager()
        source_name = data.get('source_name')
        filter_name = data.get('filter_name')
        filter_state = data.get('filter_state')
        obs_ws_manager.enable_source_filter(source_name, filter_name, filter_state)

    # ── Sequences ─────────────────────────────────────────────────────────────

    @socketio.on('trigger_sequence')
    def handle_trigger_sequence(data):
        from flask_socketio import emit
        from core.managers import get_sequence_manager
        sm          = get_sequence_manager()
        sequence_id = sm.trigger(data['sequence'], data.get('context', {}))
        socketio.emit('sequence_started', {'sequence_id': sequence_id})

    @socketio.on('request_camera_replay')
    def handle_request_camera_replay(data):
        """Like trigger_sequence(sequence='replay'), but for a specific
        camera's EventCamera row: resolves the actual replay window through
        replay_edl_builder first, so a window spanning a segment-rotation
        boundary still plays as one continuous clip instead of using the
        raw (possibly now-stale) video_path the row was created with.
        """
        from core.managers import get_sequence_manager
        from core.models.base_event_camera import get_event_camera_model
        from core.managers.replay_edl_builder import build_replay_context

        event_camera_id = data.get('event_camera_id')
        EventCamera = get_event_camera_model()
        event_camera = EventCamera.query.get(event_camera_id)
        if not event_camera:
            current_app.logger.warning(f"request_camera_replay: unknown event_camera_id={event_camera_id!r}")
            return

        context = build_replay_context(event_camera)
        sm          = get_sequence_manager()
        sequence_id = sm.trigger('replay', context)
        socketio.emit('sequence_started', {'sequence_id': sequence_id})

    @socketio.on('stop_sequence')
    def handle_stop_sequence(data):
        from flask_socketio import emit
        from core.managers import get_sequence_manager
        sm          = get_sequence_manager()
        sequence_id = data.get('sequence_id')
        if sequence_id:
            sm.stop(sequence_id)
            socketio.emit('sequence_stopped', {'sequence_id': sequence_id})
        else:
            sm.stop_all(data.get('sequence'))
            socketio.emit('all_sequences_stopped', {})

    # ── Replay export ─────────────────────────────────────────────────────────

    @socketio.on('replay_export_run')
    def handle_replay_export_run(data):
        import threading
        from flask_socketio import emit
        game_id = data.get('game_id')
        app     = current_app._get_current_object()

        def _run():
            with app.app_context():
                try:
                    from core.managers import get_replay_export_manager
                    mgr    = get_replay_export_manager()
                    result = mgr.export_game(game_id) if game_id else mgr.export_current_game()
                    from core.extensions import socketio as _sio
                    _sio.emit('replay_export_done', result)
                except Exception as e:
                    app.logger.error(f'replay_export_run error: {e}')
                    from core.extensions import socketio as _sio
                    _sio.emit('replay_export_done', {
                        'game_id': game_id, 'folder': None,
                        'files_saved': 0, 'errors': [str(e)]
                    })

        threading.Thread(target=_run, daemon=True).start()
        socketio.emit('replay_export_started', {'game_id': game_id})

    # ── Scoreboard reverse ────────────────────────────────────────────────────

    @socketio.on('reverse_scoreboard')
    def handle_reverse_scoreboard(data):
        Settings = _get_settings()
        from core.extensions import socketio as _sio
        settings = Settings.get_settings()
        settings.is_scoreboard_reversed = not settings.is_scoreboard_reversed
        from core.extensions import db
        db.session.commit()
        _sio.emit('scoreboard_reversed', {'is_reversed': settings.is_scoreboard_reversed})

    @socketio.on('set_reversed')
    def handle_set_reversed(data):
        Settings = _get_settings()
        from core.extensions import socketio as _sio
        settings = Settings.get_settings()
        settings.is_scoreboard_reversed = data.get('is_reversed', False)
        from core.extensions import db
        db.session.commit()
        _sio.emit('scoreboard_reversed', {'is_reversed': settings.is_scoreboard_reversed})

    # ── Send to overlay ───────────────────────────────────────────────────────

    @socketio.on('send_to_overlay')
    def handle_send_to_overlay(data):
        """Przekazuje dowolny sygnał bezpośrednio do overlay przez hub.

        data = { 'type': str, 'payload': any }
        """
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if hub_client:
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to':   'stream-overlay',
                'type': data.get('type'),
                'payload': data.get('payload', {}),
            })

    @socketio.on('send_background_to_obs')
    def handle_send_background_to_obs(data):
        """Zmienia plik źródła BackgroundImage w scenie STREAM przez obs-ws-plugin."""
        import os
        from core.models.base_background_image import get_background_image_model
        from core.managers import get_hub_client
        from core.extensions import db as _db

        bg_id = data.get('background_image_id')
        BG = get_background_image_model()
        bg = BG.query.get(bg_id)
        if not bg:
            return

        abs_path = os.path.join(current_app.static_folder, bg.path)

        BG.query.update({BG.is_active: False})
        bg.is_active = True
        _db.session.commit()

        hub_client = get_hub_client()
        if hub_client:
            hub_client.send({
                'from':    current_app.config['MODULE_ID'],
                'to':      'obs-ws-plugin',
                'type':    'obs_command',
                'payload': {
                    'requestType': 'SetInputSettings',
                    'requestData': {
                        'inputName':     'BackgroundImage',
                        'inputSettings': {'file': abs_path},
                        'overlay':       False,
                    }
                }
            })

    @socketio.on('send_banner_to_overlay')
    def handle_send_banner_to_overlay(data):
        """Pobiera baner z DB i wysyła go do stream-overlay przez hub."""
        from core.models.base_banner import get_banner_model
        from core.managers import get_hub_client
        banner_id = data.get('banner_id')
        Banner = get_banner_model()
        banner = Banner.query.get(banner_id)
        if not banner:
            return
        hub_client = get_hub_client()
        if hub_client:
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to':   'stream-overlay',
                'type': 'banner_show',
                'payload': {
                    'source':              banner.source,
                    'activation_function': banner.activation_function,
                },
            })

    # ── Show overlay ──────────────────────────────────────────────────────────

    @socketio.on('show_overlay_container')
    def handle_show_overlay_container(data):
        from core.managers import get_hub_client
        from core.sequences.steps import show_overlay_container
        from core.managers import session_manager
        if not session_manager.current_game_id():
            socketio.emit('error', {'message': 'Brak aktywnego meczu'})
            return
        hub_client = get_hub_client()
        if hub_client:
            step = show_overlay_container(data)
            hub_client.send({
                'from': current_app.config['MODULE_ID'],
                'to': step['target'],
                'type': step['action'],
                'payload': step['payload']
            })

    # ── Styl overlayu (stylingClass) ────────────────────────────────────────────
    # Przełączanie "skinu" overlayu: hub (nie Flask) kopiuje pliki na swoim
    # dysku (patrz hub/styling.go: handleApplyStylingClass) z
    # hub/overlays/<OVERLAY_DIR_NAME>/style/<styling_class>/{css,js}/ do
    # stałego slotu hub/overlays/<OVERLAY_DIR_NAME>/{css/style-override.css,
    # js/style-override.js}, który overlay.html ładuje zawsze, po
    # mechanizmie podstawowym — więc overlay.html nigdy nie wymaga zmian.
    # styling_class='' (albo brak) = powrót do mechanizmu podstawowego
    # (hub zeruje oba pliki slotu, nic nie kopiuje). Wybór robi się przez
    # zakładkę "MOTYWY" (/layouts/) — select_layout dostaje layout_id,
    # ustawia is_active w tabeli layouts (LayoutManager.select) i tłumaczy
    # wybrany rekord na nazwę styling_class wysyłaną do huba.

    def _send_apply_styling_class(styling_class):
        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if not hub_client:
            return
        hub_client.send({
            'from': current_app.config['MODULE_ID'],
            'to': 'hub',
            'type': 'apply_styling_class',
            'payload': {
                'overlay_dir':   current_app.config['OVERLAY_DIR_NAME'],
                'styling_class': styling_class or '',
            },
        })

    @socketio.on('select_layout')
    def handle_select_layout(data):
        from core.managers.layout_manager import LayoutManager
        selected = LayoutManager().select(data.get('layout_id') or None)
        _send_apply_styling_class(selected.name if selected else '')

    @socketio.on('register_layout')
    def handle_register_layout(data):
        # Folder motywu już istnieje na dysku (np. utworzony ręcznie) —
        # tylko dopisujemy brakujący rekord w bazie, zero operacji na
        # plikach/hubie.
        name = (data.get('name') or '').strip()
        if not name:
            return
        from core.managers.layout_manager import LayoutManager
        LayoutManager().create(name)
        socketio.emit('layout_created', {'new_name': name, 'success': True, 'error': None})

    @socketio.on('create_layout')
    def handle_create_layout(data):
        # Nowy motyw — pusty albo skopiowany z innego. Rekord w bazie
        # dopisuje hub_client po potwierdzeniu sukcesu przez huba
        # (msg_type == 'styling_class_created'), nie tutaj.
        name = (data.get('name') or '').strip()
        if not name:
            return
        source_name = ''
        source_layout_id = data.get('source_layout_id')
        if source_layout_id:
            from core.managers.layout_manager import LayoutManager
            source = LayoutManager().get_by_id(source_layout_id)
            source_name = source.name if source else ''

        from core.managers import get_hub_client
        hub_client = get_hub_client()
        if not hub_client:
            return
        hub_client.send({
            'from': current_app.config['MODULE_ID'],
            'to': 'hub',
            'type': 'create_styling_class',
            'payload': {
                'overlay_dir': current_app.config['OVERLAY_DIR_NAME'],
                'new_name':    name,
                'source_name': source_name,
            },
        })

    # ── Wywiad (interview) ──────────────────────────────────────────────────────

    def _emit_interview_participants_updated():
        from core.extensions import socketio as _sio
        from core.managers.interview_manager import InterviewManager
        Settings = _get_settings()
        game_id = session_manager.current_game_id()
        participants = InterviewManager().list_for_game(game_id) if game_id else []
        _sio.emit('interview_participants_updated', {'participants': participants})

    @socketio.on('search_interview_person')
    def handle_search_interview_person(data):
        from core.extensions import socketio as _sio
        from core.managers.interview_manager import InterviewManager
        results = InterviewManager().search_people(
            data.get('query', ''), data.get('interview_type')
        )
        _sio.emit('interview_person_results', {'results': results})

    @socketio.on('add_interview_participant')
    def handle_add_interview_participant(data):
        from core.managers.interview_manager import InterviewManager
        Settings = _get_settings()
        game_id = session_manager.current_game_id()
        if not game_id:
            return
        InterviewManager().add(
            game_id=game_id,
            interview_type=data.get('interview_type'),
            name=data.get('name', ''),
            description=data.get('description', ''),
            image_path=data.get('image_path'),
            matched_player_id=data.get('matched_player_id'),
            matched_referee_id=data.get('matched_referee_id'),
            matched_commentator_id=data.get('matched_commentator_id'),
            matched_team_id=data.get('matched_team_id'),
            use_team_crest=data.get('use_team_crest', False),
        )
        _emit_interview_participants_updated()

    @socketio.on('remove_interview_participant')
    def handle_remove_interview_participant(data):
        from core.managers.interview_manager import InterviewManager
        InterviewManager().remove(data.get('id'))
        _emit_interview_participants_updated()

    @socketio.on('reset_interview_participants')
    def handle_reset_interview_participants(data):
        from core.managers.interview_manager import InterviewManager
        Settings = _get_settings()
        game_id = session_manager.current_game_id()
        if game_id:
            InterviewManager().reset(game_id)
        _emit_interview_participants_updated()

    @socketio.on('toggle_interview_participant')
    def handle_toggle_interview_participant(data):
        from core.managers.interview_manager import InterviewManager
        InterviewManager().toggle(data.get('id'))
        _emit_interview_participants_updated()

    # ── Servo (cam-head) ──────────────────────────────────────────────────────

    @socketio.on('get_servo_heads')
    def handle_get_servo_heads():
        from flask_socketio import emit
        from core.managers import get_servo_manager
        sm = get_servo_manager()
        if sm:
            for head in sm.get_heads():
                if head.get('online'):
                    emit('servo_head_online', {'head_id': head['head_id']})

    @socketio.on('servo_set_pan_tilt')
    def handle_servo_set_pan_tilt(data):
        from core.managers import get_servo_manager
        head_id = data.get('head_id')
        pan     = data.get('pan')
        tilt    = data.get('tilt')
        if head_id and pan is not None and tilt is not None:
            get_servo_manager().set_pan_tilt(head_id, int(pan), int(tilt))

    @socketio.on('replay_control')
    def handle_replay_control(data):
        """
        Przekazuje polecenia sterowania powtórką do replay-plugin przez hub.

        Obsługiwane typy (data.type):
            pause        — pauza
            resume       — wznów
            stop         — zatrzymaj
            speed        — zmień prędkość (data.speed: float)
            frame_fwd    — krok o klatkę do przodu (wymaga pauzy)
            frame_back   — krok o klatkę do tyłu (wymaga pauzy)
            cancel_timer — cancel_time_dependent_replay_end
            end          — end_replay (tylko w trybie ręcznym)
        """
        from core.managers import get_hub_client
        hub = get_hub_client()
        if not hub:
            return

        cmd_type = data.get('type')
        type_to_signal = {
            'pause':        'replay_pause',
            'resume':       'replay_resume',
            'stop':         'replay_stop',
            'speed':        'replay_speed',
            'frame_fwd':    'replay_frame_forward',
            'frame_back':   'replay_frame_back',
            'cancel_timer': 'cancel_time_dependent_replay_end',
            'end':          'end_replay',
        }
        signal = type_to_signal.get(cmd_type)
        if not signal:
            current_app.logger.warning(f'[replay_control] Nieznany typ: {cmd_type}')
            return

        payload = {}
        if cmd_type == 'speed':
            payload['speed'] = data.get('speed', 0.9)

        hub.send({
            'from':    current_app.config.get('MODULE_ID', 'main-module'),
            'to':      'replay-plugin',
            'type':    signal,
            'payload': payload,
        })
        current_app.logger.info(f'[replay_control] {cmd_type} → {signal}')

    # ── Kandydaci zgłoszeń od pomocnika (patrz docs/helper-app-design.md) ──────

    @socketio.on('get_helper_candidates')
    def handle_get_helper_candidates(data):
        """data = { 'league_id': int }"""
        from flask_socketio import emit
        from core.managers import get_helper_relay_manager
        league_id = data.get('league_id')
        candidates = get_helper_relay_manager().get_pending_candidates(league_id)
        emit('helper_candidates_list', {
            'league_id': league_id,
            'candidates': [c.to_dict() for c in candidates],
        })

    @socketio.on('approve_helper_candidate')
    def handle_approve_helper_candidate(data):
        """data = { 'candidate_id': int }"""
        from core.extensions import socketio as _sio
        from core.managers import get_helper_relay_manager
        try:
            candidate = get_helper_relay_manager().approve_candidate(data.get('candidate_id'))
            _sio.emit('helper_candidate_resolved', candidate.to_dict())
        except ValueError as e:
            _sio.emit('helper_candidate_error', {'error': str(e)})

    @socketio.on('reject_helper_candidate')
    def handle_reject_helper_candidate(data):
        """data = { 'candidate_id': int, 'reason': str (opcjonalne) }"""
        from core.extensions import socketio as _sio
        from core.managers import get_helper_relay_manager
        try:
            candidate = get_helper_relay_manager().reject_candidate(
                data.get('candidate_id'), reason=data.get('reason'))
            _sio.emit('helper_candidate_resolved', candidate.to_dict())
        except ValueError as e:
            _sio.emit('helper_candidate_error', {'error': str(e)})


def handle_ui_monitor_content(data, extra_handler=None):
    """
    Wspólna logika request_ui_monitor_content.
    extra_handler — opcjonalna funkcja z modułu obsługująca content_type
    specyficzne dla modułu. Zwraca dict lub None.
    """
    content_type = data.get('type')
    # Wspólne content_type obsługiwane przez core
    result = _handle_core_content(content_type, data)

    # Jeśli core nie obsłużył — przekaż do modułu
    if result is None and extra_handler:
        result = extra_handler(content_type, data)

    if result is None:
        result = {'error': f'Unknown content_type: {content_type}'}

    from core.extensions import socketio
    socketio.emit('show_ui_monitor_content', result)


def _handle_core_content(content_type, data):
    """Obsługuje content_type wspólne dla wszystkich modułów."""
    if content_type is None:
        return {'content_type': None}

    if content_type == 'events':
        from core.managers.event_manager import EventManager
        from core.managers.game_event_manager import GameEventManager
        from core.managers.game_manager import GameManager
        Settings = _get_settings()
        settings = Settings.get_settings()
        game = GameManager().get_game_by_id(session_manager.current_game_id())
        
        gem        = GameEventManager()
        event_mgr  = EventManager()

        payload       = data.get('payload') or {}
        include_hidden = bool(payload.get('include_hidden', False))
        events_types = [e.to_dict() for e in event_mgr.get_all_events()]
        game_events  = []
        for period in game.get_periods_list():
            period_events = gem.get_events_for_game(session_manager.current_game_id(),
                                                    period_id=period.id,
                                                    include_hidden=include_hidden)
            if period_events:
                game_events.extend(e.to_dict() for e in period_events)
                game_events.append(period.description)

        return {
            'content_type': 'events',
            'events_types': events_types,
            'game_events':  game_events,
        }

    elif content_type == 'interview':
        from core.managers.interview_manager import InterviewManager
        Settings = _get_settings()
        game_id = session_manager.current_game_id()
        participants = InterviewManager().list_for_game(game_id) if game_id else []
        return {
            'content_type': 'interview',
            'participants': participants,
        }

    elif content_type == 'edit_event':
        from core.managers.event_manager import EventManager
        Settings = _get_settings()

        payload      = data.get('payload', {})
        game_event_d = _get_game_event_data(payload['game_event_id'])
        events_types = [
            e.to_dict() for e in EventManager().get_all_events()
            if e.filter_class
        ]
        return {
            'content_type':          'edit_event',
            'events_types':          events_types,
            'is_scoreboard_reversed': bool(Settings.get_settings().is_scoreboard_reversed),
            'team_squad':            game_event_d['team_squad'],
            'game_event':            game_event_d['game_event'],
            'home_team_id':          game_event_d['home_team_id'],
            'away_team_id':          game_event_d['away_team_id'],
            'home_team_short_name':  game_event_d['home_team_short_name'],
            'away_team_short_name':  game_event_d['away_team_short_name'],
        }

    elif content_type == 'get_event_squad':
        payload      = data.get('payload', {})
        new_team_id  = payload['new_team_id'] if 'new_team_id' in payload else _TEAM_ID_NOT_SET
        game_event_d = _get_game_event_data(
            payload['game_event_id'], payload.get('new_event_type_id'), new_team_id
        )
        return {
            'content_type': 'get_event_squad',
            'game_event':   game_event_d['game_event'],
            'team_squad':   game_event_d['team_squad'],
        }
    elif content_type == 'games':
        from core.managers.game_manager import GameManager
        from core.managers.league_manager import LeagueManager
        from core.models.base_settings import get_settings_model
        from datetime import date

        payload    = data.get('payload') or {}
        league_id  = payload.get('league_id')
        date_from  = payload.get('date_from', date.today().isoformat())
        date_to    = payload.get('date_to', date_from)

        league_manager = LeagueManager()
        Settings = get_settings_model()
        settings = Settings.get_settings()

        # Domyślnie: liga aktualnie transmitowanego meczu
        if league_id is None:
            current_game = GameManager().get_game_by_id(session_manager.current_game_id())
            league_id = current_game.league_id if current_game else None

        # Zakładki ligowe ograniczone do JEDNEGO sezonu — sezonu wybranej
        # (albo domyślnej) ligi, a gdy tej nie da się ustalić, aktualnego
        # sezonu z Settings. Różne sezony nie powinny mieszać się w jednym
        # pasku zakładek (patrz Settings.current_season_id).
        season_id = None
        if league_id:
            selected_league = league_manager.get_league_by_id(league_id)
            season_id = selected_league.season_id if selected_league else None
        if season_id is None:
            season_id = settings.current_season_id

        from core.extensions import db
        from core.models.base_game import get_game_model
        Game = get_game_model()

        leagues = league_manager.get_all_leagues(season_id=season_id) if season_id else []

        # Dołącz max_group_nr per liga (potrzebne do standings fetch w JS)
        leagues_data = []
        for l in leagues:
            d = l.to_dict()
            max_grp = (
                db.session.query(db.func.max(Game.group_nr))
                .filter(Game.league_id == l.id)
                .scalar()
            )
            d['max_group_nr'] = max_grp or 1
            leagues_data.append(d)

        games = GameManager().get_all_games(
            league_id=league_id,
            date_from=date_from,
            date_to=date_to,
        ) if league_id else []

        return {
            'content_type': 'games',
            'league_id':    league_id,
            'date_from':    date_from,
            'date_to':      date_to,
            'leagues':      leagues_data,
            'games':        [g.to_dict() for g in games],
        }

    elif content_type == 'banners':
        from core.models.base_banner import get_banner_model
        Banner = get_banner_model()
        banners = Banner.query.order_by(Banner.order).all()
        return {
            'content_type': 'banners',
            'banners': [b.to_dict() for b in banners],
        }

    elif content_type == 'backgrounds':
        from core.models.base_background_image import get_background_image_model
        BG = get_background_image_model()
        backgrounds = BG.query.order_by(BG.order, BG.name).all()
        active = BG.query.filter_by(is_active=True).first()
        return {
            'content_type':      'backgrounds',
            'backgrounds':       [b.to_dict() for b in backgrounds],
            'active_background': active.to_dict() if active else None,
        }

    return None  # nieznany — przekaż do modułu

