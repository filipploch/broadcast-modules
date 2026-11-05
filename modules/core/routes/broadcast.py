"""
core.routes.broadcast — trasy wspólne dla wszystkich modułów.

Obsługuje: timer UI, sterowanie okresami, sekwencje, nagrywanie,
           API statusu i ustawień.

Każdy moduł rejestruje te trasy przez:
    from core.routes import broadcast as core_broadcast
    core_broadcast.register_routes(app)
"""
from core.managers import session_manager
from core.managers.timer_manager import current_timers_for_game, recovery_timers_for_game
from flask import (render_template, jsonify, current_app,
                   flash, redirect, url_for, request)
from core.managers.season_manager import SeasonManager
from core.managers.league_manager import LeagueManager
from core.managers.game_manager import GameManager
from core.managers.camera_manager import CameraManager
from core.managers.game_camera_manager import GameCameraManager
from core.extensions import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

season_manager = SeasonManager()
league_manager = LeagueManager()
game_manager = GameManager()

def _get_team():
    from core.models.base_team import get_team_model
    return get_team_model()

def _get_player():
    from core.models.base_player import get_player_model
    return get_player_model()

def _get_settings():
    from core.models.base_settings import get_settings_model
    return get_settings_model()

def _get_game():
    from core.models.base_game import get_game_model
    return get_game_model()

def _get_period():
    from core.models.base_period import get_period_model
    return get_period_model()


def register_routes(app, exclude=None):
    exclude = exclude or set()
    """Rejestruje wspólne trasy w instancji Flask aplikacji."""

    @app.route('/wp/competitions')
    def wp_competitions():
        """Rozgrywki z WordPressa modułu: lista, wybór i rozgrywki domyślne (WP-2)."""
        return render_template('wp/competitions.html')

    @app.route('/api/wp/state')
    def api_wp_state():
        from core.managers import get_wp_manager
        return jsonify(get_wp_manager().state())

    @app.route('/api/wp/pull', methods=['POST'])
    def api_wp_pull():
        """Podgląd (apply=false) albo zapis (apply=true) zaznaczonej pary z WP do bazy modułu (W7a). Odpowiedź: wynik jak w WpManager.pull."""
        import os
        from pathlib import Path
        from core.extensions import db
        from core.managers import get_wp_manager
        data = request.get_json(silent=True) or {}
        logo_root = Path(__file__).resolve().parents[2] / 'static' / 'images' / 'logos'
        folder = Path(current_app.config.get('MODULE_DIR') or os.getcwd()).name
        kopie = Path(current_app.config.get('WP_PULL_COPIES_DIR') or Path(current_app.instance_path) / 'kopie-wp')
        wynik = get_wp_manager().pull(bool(data.get('apply')), db, logo_root, folder, kopie, data.get('league_id'), data.get('season_id'))
        return jsonify(wynik)

    # -- W8a2: „Pobierz” ze źródła zewnętrznego (źródło -> WP -> moduł); przycisk jest ukryty, gdy moduł nie ma źródła
    def _klucz_pary_ligi(league_id):
        """'liga_wp:sezon_wp' ligi modułu pobranej z WP (LeagueForeignId) albo None."""
        from core.models.base_league_foreign_id import get_league_foreign_id_model
        from core.models.base_scraper import get_scraper_model
        sc = get_scraper_model().get_by_folder('wp')
        if sc is None:
            return None
        w = get_league_foreign_id_model().query.filter_by(scraper_id=sc.id, league_id=int(league_id)).first()
        return w.foreign_id if w else None

    @app.route('/api/zrodlo/status')
    def api_zrodlo_status():
        from core.managers import get_wp_manager, get_zrodlo
        return jsonify(get_zrodlo().status(get_wp_manager().cfg.enabled))

    @app.route('/api/zrodlo/pobierz', methods=['POST'])
    def api_zrodlo_pobierz():
        """Rozpoczyna „Pobierz wyniki” dla ligi (body: league_id; bez niego - wybór domyślny rozgrywek). Praca idzie w tle, stan: /api/zrodlo/status."""
        import os
        from pathlib import Path
        from core.extensions import db
        from core.managers import get_wp_manager, get_zrodlo
        z, wp = get_zrodlo(), get_wp_manager()
        dost, powod = z.dostepne(wp.cfg.enabled)
        if not dost:
            return jsonify({'ok': False, 'error': f'Pobieranie ze źródła niedostępne: {powod}.'}), 409
        league_id = (request.get_json(silent=True) or {}).get('league_id')
        klucz = _klucz_pary_ligi(league_id) if league_id not in (None, '') else None
        para, blad = z.rozwiaz(None if league_id in (None, '') else int(league_id), wp.state(), klucz)
        if blad:
            return jsonify({'ok': False, 'error': blad}), 409
        app_obj = current_app._get_current_object()
        logo_root = Path(__file__).resolve().parents[2] / 'static' / 'images' / 'logos'
        folder = Path(app_obj.config.get('MODULE_DIR') or os.getcwd()).name
        kopie = Path(app_obj.config.get('WP_PULL_COPIES_DIR') or Path(app_obj.instance_path) / 'kopie-wp')

        def pobranie(p):
            with app_obj.app_context():
                return wp.pull(True, db, logo_root, folder, kopie, p['liga_wp'], p['sezon_wp'])
        ok, komunikat = z.start(para, pobranie)
        if not ok:
            return jsonify({'ok': False, 'error': komunikat}), 409
        return jsonify({'ok': True, 'status': 'started', 'liga': para['nazwa']}), 202

    # -- W8b: tabela ligowa z WP na żądanie (źródło prawdy o tabeli; moduł jej nie liczy, nic nie buforuje i nie odświeża w tle)
    @app.route('/api/wp-tabela')
    def api_wp_tabela():
        """Tabela ligi modułu z WP (bm/v1/table). Query: league_id (liga modułu), mode=final|live. Sukces: {ok, mode, rows (pola jak dotąd w panelu),
        warnings, computed_at, engine, matches_counted, live_matches}. Błąd: {ok: false, error, kind} z kodem 404 (liga bez tabeli, np. puchar),
        409 (liga nie pochodzi z WP) albo 503 (WP nie odpowiada, odrzucił logowanie, zła wersja wtyczki); panel pokazuje wtedy wyraźny komunikat."""
        from core.managers import get_wp_manager
        from core.managers.wp_client import WpClient, WpError
        mode = request.args.get('mode', 'final')
        if mode not in ('final', 'live'):
            return jsonify({'ok': False, 'error': 'Tryb tabeli musi być final albo live.', 'kind': 'param'}), 400
        try:
            league_id = int(request.args.get('league_id'))
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Brak wybranej ligi.', 'kind': 'param'}), 400
        wp = get_wp_manager()
        if not wp.cfg.enabled:
            return jsonify({'ok': False, 'error': 'Ten moduł nie ma własnej instancji WP.', 'kind': 'brak_wp'}), 409
        klucz = _klucz_pary_ligi(league_id)
        if not klucz:
            return jsonify({'ok': False, 'error': 'Ta liga nie pochodzi z WP: najpierw „Pobierz z WP” (strona Rozgrywki WP).', 'kind': 'nie_z_wp'}), 409
        liga_wp, sezon_wp = klucz.split(':', 1)
        try:
            odp = WpClient(wp.cfg, timeout=20).get_json('bm/v1/table', {'league': liga_wp, 'season': sezon_wp, 'mode': mode})
        except WpError as e:
            if e.kind == 'http' and e.code == 'bm_no_table':
                return jsonify({'ok': False, 'error': 'Rozgrywki tej ligi nie mają tabeli (np. puchar).', 'kind': 'brak_tabeli'}), 404
            if e.kind == 'http' and e.code == 'rest_no_route':
                return jsonify({'ok': False, 'error': 'WP nie ma trasy tabeli: wtyczka bm-pomocnik w WP jest w starej wersji.', 'kind': 'stara_wtyczka'}), 503
            powod = {'connection': 'WP nie odpowiada', 'auth': 'WP odrzucił dane logowania'}.get(e.kind, 'Błąd rozmowy z WP')
            return jsonify({'ok': False, 'error': f'Tabela niedostępna: {powod} ({e}).', 'kind': e.kind}), 503
        if not isinstance(odp, dict) or not isinstance(odp.get('rows'), list):
            return jsonify({'ok': False, 'error': 'Tabela niedostępna: WP zwrócił odpowiedź w nieoczekiwanym formacie.', 'kind': 'format'}), 503

        def wiersz(r):               # nazwy pól jak w dotychczasowej tabeli panelu i nakładek
            return {'position': r.get('pos'), 'wp_team_id': r.get('team_id'), 'team_name': r.get('name') or '', 'team_name_14': r.get('name14') or r.get('name') or '',
                    'team_short_name': r.get('short') or '', 'games': r.get('p', 0), 'wins': r.get('w', 0), 'draws': r.get('d', 0), 'loses': r.get('l', 0),
                    'goals_scored': r.get('f', 0), 'goals_lost': r.get('a', 0), 'goal_difference': r.get('gd', 0), 'points': r.get('pts', 0), 'away_wins': r.get('wa', 0)}
        return jsonify({'ok': True, 'mode': odp.get('mode', mode), 'rows': [wiersz(r) for r in odp['rows']], 'warnings': odp.get('warnings') or [],
                        'computed_at': odp.get('computed_at', ''), 'engine': odp.get('engine', ''), 'matches_counted': odp.get('matches_counted', 0),
                        'live_matches': odp.get('live_matches', 0)})

    # -- W8a: zapis stanu i wyniku meczu do WP (kolejka, wyłącznik) i świadome zakończenie meczu

    def _nazwa_meczu(game):
        return f'{game.home_team.name} – {game.away_team.name}' if game is not None and game.home_team and game.away_team else ''

    def _niezakonczone():
        """Bieżący mecz, którego wszystkie części są zakończone, a który nie jest oznaczony jako zakończony (pasek „Mecz nie jest zakończony”)."""
        Game, Settings = _get_game(), _get_settings()
        settings = Settings.get_settings()
        game = Game.query.get(settings.current_game_id) if settings.current_game_id else None
        if game is None or game.status == Game.STATUS_FINISHED:
            return []
        okresy = game.get_periods_list()
        Period = _get_period()
        if not okresy or not all(p.status == Period.STATUS_FINISHED for p in okresy):
            return []
        remis = bool(game.league is not None and not game.league.allows_draw and game.home_team_goals is not None
                     and game.home_team_goals == game.away_team_goals and game.shootout is None)
        return [{'game_id': game.id, 'nazwa': _nazwa_meczu(game), 'wynik': f'{game.home_team_goals}:{game.away_team_goals}',
                 'remis_bez_rozstrzygniecia': remis}]

    @app.route('/api/wp-zapis/status')
    def api_wp_zapis_status():
        from core.managers.wp_zapis import get_wp_zapis, WpZapis
        z = get_wp_zapis()
        s = z.status() if z is not None else WpZapis.status_nieaktywny()
        Game = _get_game()
        for o in s['odrzucone']:
            o['nazwa'] = _nazwa_meczu(Game.query.get(o['game_id']))
        s['niezakonczone'] = _niezakonczone()
        return jsonify(s)

    @app.route('/api/wp-zapis/wlacznik', methods=['POST'])
    def api_wp_zapis_wlacznik():
        from core.managers.wp_zapis import get_wp_zapis
        z = get_wp_zapis()
        if z is None or not z.skonfigurowany:
            return jsonify({'error': 'Zapis do WP nie jest skonfigurowany dla tej bazy'}), 400
        z.ustaw_wlaczony(bool((request.get_json(silent=True) or {}).get('wlaczony', True)))
        return jsonify(z.status())

    @app.route('/api/wp-zapis/ponow', methods=['POST'])
    def api_wp_zapis_ponow():
        from core.managers.wp_zapis import get_wp_zapis
        z = get_wp_zapis()
        if z is None or not z.skonfigurowany:
            return jsonify({'error': 'Zapis do WP nie jest skonfigurowany dla tej bazy'}), 400
        z.ponow_teraz()
        return jsonify(z.status())

    @app.route('/api/games/<int:game_id>/finish', methods=['POST'])
    def api_finish_game(game_id):
        """Świadome zakończenie meczu przez operatora (okno „Zakończyć mecz?” albo pasek „Mecz nie jest zakończony”)."""
        Game = _get_game()
        game = Game.query.get(game_id)
        if game is None:
            return jsonify({'error': 'Nie znaleziono meczu'}), 404
        if game.status != Game.STATUS_FINISHED:
            game.set_finished()
            db.session.commit()
        try:                                                   # po zakończeniu meczu żaden zegar nie biegnie (także po nieudanym zatrzymaniu przy końcu części)
            from core.managers import get_timer_manager
            get_timer_manager().pause_game_timers(game.id)
        except Exception as e:
            logger.warning(f'Zakończenie meczu {game.id}: nie udało się zatrzymać zegarów: {e}')
        return jsonify({'ok': True, 'game_id': game.id, 'status': game.status})

    @app.route('/api/status')
    def api_status():
        return jsonify({
            'status': 'running',
            'module_id': current_app.config['MODULE_ID']
        })

    @app.route('/api/scoreboard-state', methods=['GET', 'POST'])
    def get_scoreboard_state():
        from core.models.base_settings import get_settings_model
        Settings = get_settings_model()
        from datetime import datetime
        settings = Settings.query.get(1)
        if not settings:
            settings = Settings(id=1, is_scoreboard_reversed=False)
            db.session.add(settings)
            db.session.commit()
        if request.method == 'POST':
            data = request.get_json()
            settings.is_scoreboard_reversed = data.get('is_reversed', False)
            settings.updated_at = datetime.utcnow()
            db.session.add(settings)
            db.session.commit()
            return jsonify({'success': True, 'is_reversed': settings.is_scoreboard_reversed})
        return jsonify({'is_reversed': settings.is_scoreboard_reversed})

    @app.route('/api/settings/current-timers')
    def api_current_timers():
        return jsonify(current_timers_for_game())

    @app.route('/api/settings/current-timers/clear', methods=['POST'])
    def api_clear_current_timers():
        # Od E1 zegary są wyliczane z okresu i GameTimer, nie przechowywane; endpoint zostaje jako pusta operacja.
        return jsonify({'success': True, 'message': 'No-op: timers are derived from the current period'})

    @app.route('/api/replay-export/current', methods=['POST'])
    def api_replay_export_current():
        from core.managers import get_replay_export_manager
        try:
            mgr = get_replay_export_manager()
            result = mgr.export_current_game()
            status = 200 if not result['errors'] else 207
            return jsonify(result), status
        except Exception as e:
            logger.error(f"api_replay_export_current: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/replay-export/<int:game_id>', methods=['POST'])
    def api_replay_export_run(game_id):
        from core.managers import get_replay_export_manager
        try:
            mgr = get_replay_export_manager()
            result = mgr.export_game(game_id)
            status = 200 if not result['errors'] else 207
            return jsonify(result), status
        except Exception as e:
            logger.error(f"api_replay_export_run({game_id}): {e}")
            return jsonify({'game_id': game_id, 'error': str(e)}), 500
        

    @app.route('/api/settings')
    def api_get_settings():
        """
        Get complete settings including current period, game and timers
    
        Used by timer recovery system to check what timers should be running
        after crash/restart.
    
        Returns JSON:
        {
            "current_season_id": int or null,
            "current_game_id": int or null,
            "current_period_id": int or null,
            "current_timers": {
                "main": {
                    "timer_id": "main-p1",
                    "state": "running",
                    "initial_time": 0,
                    "limit": 1200000,
                    ...
                } or null,
                "penalties": [
                    {
                        "timer_id": "penalty-1",
                        "state": "running",
                        ...
                    }
                ]
            },
            "period": {
                "id": int,
                "description": str,
                "main_timer_name": str,
                "initial_time": int,
                "limit": int,
                "pause_at_limit": bool,
                "status": int
            } or null,
            "game": {
                "id": int
            } or null
        }
        """
    
    
        Game = _get_game()
        Settings = _get_settings()
        Period = _get_period()
    
        settings = Settings.get_settings()
        current_timers = current_timers_for_game()
    
        # Get period details if exists
        period_data = None
        if session_manager.current_period_id():
            period = Period.query.get(session_manager.current_period_id())
            if period:
                period_data = {
                    "id": period.id,
                    "description": period.description,
                    "period_order": period.period_order,
                    "main_timer_name": period.main_timer_name,
                    "initial_time": period.initial_time,
                    "limit": period.limit,
                    "pause_at_limit": period.pause_at_limit,
                    "status": period.status
                }
    
        # Get game details if exists
        game_data = None
        if session_manager.current_game_id():
            game = Game.query.get(session_manager.current_game_id())
            if game:
                game_data = {
                    "id": game.id,
                    # Add other game fields as needed
                }

        is_reversed = False
        if settings.is_scoreboard_reversed:
            is_reversed = True
    
        return jsonify({
            "current_season_id": session_manager.current_season_id(),
            "current_game_id": session_manager.current_game_id(),
            "current_period_id": session_manager.current_period_id(),
            "current_timers": current_timers,
            "recovery_timers": recovery_timers_for_game(),
            "period": period_data,
            "game": game_data,
            "is_reversed": is_reversed,
            "session": session_manager.describe()
        })

    # ── Sesja transmisji (E1) ────────────────────────────────────────────────
    def _session_response(action, **kwargs):
        from core.extensions import socketio
        try:
            getattr(session_manager, action)(**kwargs)
        except session_manager.SessionError as e:
            return jsonify({'success': False, 'error': str(e), 'session': session_manager.describe()}), 409
        state = session_manager.describe()
        socketio.emit('session_state', state)
        return jsonify({'success': True, 'session': state})

    @app.route('/api/session')
    def api_session():
        """Stan sesji transmisji: {'open': False} albo status, aktywny mecz, okres, stan OBS i kolejka."""
        return jsonify(session_manager.describe())

    @app.route('/api/session/open', methods=['POST'])
    def api_session_open():
        return _session_response('open_session')

    @app.route('/api/session/go-on-air', methods=['POST'])
    def api_session_go_on_air():
        """Ręczne przejście 'na antenie' (uzupełnienie automatu: start streamu/nagrywania w OBS)."""
        if session_manager.get_open_session() is None:
            return jsonify({'success': False, 'error': 'Brak otwartej sesji transmisji.', 'session': {'open': False}}), 409
        return _session_response('go_on_air')

    @app.route('/api/session/next-game', methods=['POST'])
    def api_session_next_game():
        """Jawna akcja 'następny mecz': kończy aktywny mecz i aktywuje następny z kolejki; stream trwa dalej."""
        return _session_response('next_game')

    @app.route('/api/session/close', methods=['POST'])
    def api_session_close():
        """Zamknięcie sesji — wyłącznie ręczne; nigdy automatycznie po zatrzymaniu streamu."""
        return _session_response('close_session')

    @app.route('/api/stadium-camera-positions')
    def api_stadium_camera_positions():
        stadium_id = request.args.get('stadium_id', type=int)
        if not stadium_id:
            return jsonify([])
        from core.models.base_stadium_camera_position import get_stadium_camera_position_model
        StadiumCameraPosition = get_stadium_camera_position_model()
        positions = (
            StadiumCameraPosition.query
            .filter_by(stadium_id=stadium_id)
            .order_by(StadiumCameraPosition.sort_order)
            .all()
        )
        return jsonify([p.to_dict() for p in positions])

    @app.route('/api/stadium-camera-positions/<int:position_id>', methods=['PATCH'])
    def api_update_stadium_camera_position(position_id):
        from core.models.base_stadium_camera_position import get_stadium_camera_position_model
        pos = get_stadium_camera_position_model().query.get_or_404(position_id)
        data = request.get_json(silent=True) or {}
        if 'default_camera_id' in data:
            pos.default_camera_id = data['default_camera_id']
        db.session.commit()
        return jsonify(pos.to_dict())

    @app.route('/api/cameras')
    def api_cameras():
        from core.models.base_camera import get_camera_model
        cams = get_camera_model().query.order_by('name').all()
        return jsonify([c.to_dict() for c in cams])

    @app.route('/api/cameras/<int:camera_id>', methods=['PATCH'])
    def api_update_camera_field(camera_id):
        from core.models.base_camera import get_camera_model
        cam = get_camera_model().query.get_or_404(camera_id)
        data = request.get_json(silent=True) or {}
        if 'cam_head_id' in data:
            cam.cam_head_id = data['cam_head_id']
        db.session.commit()
        return jsonify(cam.to_dict())

    @app.route('/api/cam-heads')
    def api_cam_heads():
        from core.models.base_cam_head import get_cam_head_model
        heads = get_cam_head_model().query.order_by('name').all()
        return jsonify([h.to_dict() for h in heads])

    @app.route('/api/camera-position-calibrations')
    def api_camera_position_calibrations():
        position_id = request.args.get('position_id', type=int)
        camera_id   = request.args.get('camera_id',   type=int)
        if not position_id:
            return jsonify([])
        from core.models.base_camera_position_calibration import get_camera_position_calibration_model
        Cal = get_camera_position_calibration_model()
        q = Cal.query.filter_by(position_id=position_id, camera_id=camera_id)
        return jsonify([c.to_dict() for c in q.all()])

    @app.route('/api/camera-position-calibrations', methods=['PUT'])
    def api_upsert_camera_position_calibration():
        data        = request.get_json(silent=True) or {}
        position_id = data.get('position_id')
        camera_id   = data.get('camera_id')
        zone_code   = data.get('zone_code')
        pan         = data.get('pan')
        tilt        = data.get('tilt')
        if position_id is None or zone_code is None or pan is None or tilt is None:
            return jsonify({'error': 'Missing required fields'}), 400
        from core.models.base_camera_position_calibration import get_camera_position_calibration_model
        Cal = get_camera_position_calibration_model()
        cal = Cal.query.filter_by(
            position_id=position_id,
            camera_id=camera_id,
            zone_code=zone_code,
        ).first()
        if cal:
            cal.pan  = pan
            cal.tilt = tilt
        else:
            cal = Cal(position_id=position_id, camera_id=camera_id,
                      zone_code=zone_code, pan=pan, tilt=tilt)
            db.session.add(cal)
        db.session.commit()
        return jsonify(cal.to_dict())