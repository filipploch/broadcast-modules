"""
app.routes.futsal — trasy specyficzne dla modułu futsal-nalf.

Zawiera trasy z oryginalnych routes.py i routes_crud.py.
Rejestracja przez: futsal_routes.register_routes(app)
"""
from flask import (render_template, jsonify, current_app,
                   flash, redirect, url_for, request)
from core.extensions import db
from app.managers import (
    GameManager, TeamManager, LeagueManager, SeasonManager,
    GameEventManager, CameraManager, GameCameraManager,
    CommentatorManager, GameScraperManager, GameCommentatorManager,
    RefereeManager, TeamScraperManager, GameRefereeManager,
    GamePlayerManager, PlayerScraperManager, PlayerManager,
    StadiumManager, EventManager,
)
# from app.managers.game_scraper_manager import GameScraperManager
# from app.managers.team_scraper_manager import TeamScraperManager
# from app.managers.player_scraper_manager import PlayerScraperManager
from app.models.period import Period
from app.models.settings import Settings
import logging
import os

logger = logging.getLogger(__name__)

game_manager           = GameManager()
team_manager           = TeamManager()
team_scraper_manager   = TeamScraperManager()
player_scraper_manager = PlayerScraperManager()
game_scraper_manager   = GameScraperManager()
league_manager         = LeagueManager()


def register_routes(app):
    """Rejestruje wszystkie trasy specyficzne dla futsal-nalf."""
    """Rejestruje wszystkie trasy specyficzne dla futsal-nalf."""

    # Import routes_crud i routes — dodaj ich zawartość jako funkcje wewnętrzne
    # przez użycie @app.route zamiast @current_app.route

    from flask import render_template, jsonify, current_app, flash, redirect, url_for, request

    # from app.models import Plugin





    # from app.managers import get_game_manager


    from app.models.team import Team


    import logging
    from datetime import datetime
    import os

    # Import CRUD routes for Season, League, Game
    from core.routes import routes_crud  # noqa: F401


    logger = logging.getLogger(__name__)

    team_manager = TeamManager()
    team_scraper_manager = TeamScraperManager()
    player_scraper_manager = PlayerScraperManager()
    # game_manager = GameManager()
    game_scraper_manager = GameScraperManager()
    # league_manager = LeagueManager()


    @app.route('/api/assign/<content_type>/data')
    def api_assign_data(content_type):
        """Return JSON with assigned and available elements for the assignment modal."""
        from flask import jsonify
    
        from app.models.game import Game
        # from app.managers.game_player_manager import GamePlayerManager
        # from core.managers.player_manager import PlayerManager
        # from core.managers.game_referee_manager import GameRefereeManager
        # from core.managers.referee_manager import RefereeManager
        # from core.managers.game_commentator_manager import GameCommentatorManager
        # from core.managers.commentator_manager import CommentatorManager
        # from core.managers.game_camera_manager import GameCameraManager
        # from core.managers.camera_manager import CameraManager
        from app.models.game_camera import VALID_HDMI_INPUTS, HDMI_DEFAULT_LOCATION
        from app.models.player import Player

        settings = Settings.get_settings()
        if not settings.current_game_id:
            return jsonify({'error': 'Brak wybranego meczu'}), 400

        game = Game.query.get(settings.current_game_id)
        if not game:
            return jsonify({'error': 'Nie znaleziono meczu'}), 404

        game_id = game.id

        # ── home_squad / away_squad ──────────────────────────────────────────────
        if content_type in ('home-squad', 'away-squad'):
            team_id = game.home_team_id if content_type == 'home-squad' else game.away_team_id
            team    = game.home_team    if content_type == 'home-squad' else game.away_team
 
            # from app.managers.game_player_manager import GamePlayerManager as _GPM
            from app.models.game_player import ROLE_STARTER, ROLE_SUBSTITUTE
            pg_mgr = GamePlayerManager()
 
            starters    = pg_mgr.get_starters(game_id,   team_id=team_id)
            substitutes = pg_mgr.get_substitutes(game_id, team_id=team_id)
            assigned_ids = {pg.player_id for pg in starters + substitutes}
 
            def _pg_dict(pg):
                return {
                    'pg_id':        pg.id,
                    'player_id':    pg.player_id,
                    'label':        f"{pg.player.last_name} {pg.player.first_name}",
                    'last_name':    pg.player.last_name,
                    'first_name':   pg.player.first_name,
                    'number':       pg.number,
                    'is_captain':   pg.is_captain,
                    'is_goalkeeper': pg.is_goalkeeper,
                    'is_youth':     pg.is_youth,
                    'role':         pg.role,
                }
 
            all_players = (Player.query
                .filter_by(team_id=team_id)
                .order_by(Player.is_goalkeeper.desc(), Player.last_name.asc())
                .all())
            available = [{
                'player_id':    p.id,
                'label':        f"{p.last_name} {p.first_name}",
                'is_goalkeeper': p.is_goalkeeper,
                'is_youth':     p.is_youth,
                'number':       p.number,
            } for p in all_players if p.id not in assigned_ids]
 
            laczynaspilka_url = (
                f'https://www.laczynaspilka.pl/rozgrywki/druzyna/{team.foreign_id}'
                if team.foreign_id else None
            )
            return jsonify({
                'title':              f"Skład: {team.name}",
                'content_type':       content_type,
                'team_id':            team_id,
                'laczynaspilka_url':  laczynaspilka_url,
                'starters':           [_pg_dict(pg) for pg in starters],
                'substitutes':        [_pg_dict(pg) for pg in substitutes],
                'available':          available,
                'max_starters':       11,
            })

        # ── referees ─────────────────────────────────────────────────────────────
        if content_type == 'referees':
            from app.models.game_referee import GameReferee
            gr_mgr = GameRefereeManager()
            assigned_grs = gr_mgr.get_referees_for_game(game_id)
            assigned_ids = {gr.referee_id for gr in assigned_grs}

            assigned = [{
                'gr_id': gr.id,
                'referee_id': gr.referee_id,
                'label': f"{gr.referee.last_name} {gr.referee.first_name}",
                'type': gr.type,
                'types': GameReferee.REFEREE_TYPES,
            } for gr in assigned_grs]

            all_refs = RefereeManager().get_all_referees()
            available = [{
                'referee_id': r.id,
                'label': f"{r.last_name} {r.first_name}",
                'types': GameReferee.REFEREE_TYPES,
            } for r in all_refs if r.id not in assigned_ids]

            return jsonify({
                'title': 'Sędziowie',
                'content_type': content_type,
                'assigned': assigned,
                'available': available,
            })

        # ── commentators ─────────────────────────────────────────────────────────
        if content_type == 'commentators':
            from app.models.game_commentator import GameCommentator
            gc_mgr = GameCommentatorManager()
            assigned_gcs = gc_mgr.get_commentators_for_game(game_id)
            assigned_ids = {gc.commentator_id for gc in assigned_gcs}

            assigned = [{
                'gc_id': gc.id,
                'commentator_id': gc.commentator_id,
                'label': f"{gc.commentator.last_name} {gc.commentator.first_name}",
                'type': gc.type,
                'types': GameCommentator.REFEREE_TYPES,
            } for gc in assigned_gcs]

            all_cs = CommentatorManager().get_all_commentators()
            available = [{
                'commentator_id': c.id,
                'label': f"{c.last_name} {c.first_name}",
                'types': GameCommentator.REFEREE_TYPES,
            } for c in all_cs if c.id not in assigned_ids]

            return jsonify({
                'title': 'Komentatorzy',
                'content_type': content_type,
                'assigned': assigned,
                'available': available,
            })

        # ── cameras ───────────────────────────────────────────────────────────────
        if content_type == 'cameras':
            gc_mgr = GameCameraManager()
            assigned_gcs = gc_mgr.get_cameras_for_game(game_id)
            assigned_ids = {gc.camera_id for gc in assigned_gcs}
            free_hdmi = gc_mgr.get_available_hdmi_inputs(game_id)

            assigned = [{
                'gc_id': gc.id,
                'camera_id': gc.camera_id,
                'label': gc.camera.name,
                'sub': f"{gc.camera.brand} {gc.camera.model}",
                'hdmi_input': gc.hdmi_input,
                'location': gc.location,
                'is_motorized': gc.is_motorized,
                'free_hdmi': free_hdmi,
                'hdmi_labels': HDMI_DEFAULT_LOCATION,
            } for gc in assigned_gcs]

            all_cameras = CameraManager().get_all_cameras()
            available = [{
                'camera_id': c.id,
                'label': c.name,
                'sub': f"{c.brand} {c.model}",
                'free_hdmi': free_hdmi,
                'hdmi_labels': HDMI_DEFAULT_LOCATION,
            } for c in all_cameras if c.id not in assigned_ids]

            return jsonify({
                'title': 'Kamery',
                'content_type': content_type,
                'assigned': assigned,
                'available': available,
            })

        return jsonify({'error': f'Nieznany typ: {content_type}'}), 400



    @app.route('/teams/<int:team_id>')
    def view_team(team_id):
        """View single team details"""
        team = team_manager.get_team_by_id(team_id)

        if not team:
            flash('Nie znaleziono zespołu', 'error')
            return redirect(url_for('list_teams'))

        logos_dir = 'static/images/logos'
        with current_app.app_context():
            module_name = current_app.config['MODULE_NAME']
            logos_dir = f'static/images/logos/{module_name}'
        logos = []

        if os.path.exists(logos_dir):
            allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
            for file in os.listdir(logos_dir):
                if any(file.lower().endswith(ext) for ext in allowed_extensions):
                    logos.append({
                        'filename': file,
                        'path': f'/static/images/logos/{module_name}/{file}'
                    })

        return render_template('teams/view.html', team=team)


    @app.route('/teams/')
    def list_teams():
        """List all teams in database"""
        teams = team_manager.get_all_teams()
        stats = team_scraper_manager.get_statistics()
        scraping_status = team_scraper_manager.get_scraping_status()

        return render_template('teams/list.html',
                               teams=teams,
                               stats=stats,
                               scraping_status=scraping_status)



    @app.route('/teams/<int:team_id>/scrape-players')
    def scrape_players(team_id):
        from flask import jsonify
        from app.models.team import Team

        if player_scraper_manager.is_scraping_in_progress():
            return jsonify({'error': 'Scrapowanie zawodników już trwa'}), 409

        team = Team.query.get(team_id)
        if not team:
            return jsonify({'error': 'Nie znaleziono drużyny'}), 404

        if not team.foreign_id:
            return jsonify({'error': 'Drużyna nie ma skonfigurowanego foreign_id'}), 400

        if not player_scraper_manager.check_file_exists(team_id):
            url = f'https://www.laczynaspilka.pl/rozgrywki/druzyna/{team.foreign_id}'
            return jsonify({
                'error': 'file_missing',
                'team_name': team.name,
                'url': url,
            }), 404

        started = player_scraper_manager.scrape_players_async(team_id)
        if started:
            return jsonify({'status': 'started'}), 202
        return jsonify({'error': 'Nie można rozpocząć scrapowania'}), 400

    # =========================
    # ASSIGNMENT API
    # =========================


    @app.route('/teams/pending')
    def pending_teams():
        """List pending teams from scraping that need completion"""
        pending = team_scraper_manager.get_pending_teams()
        logos = team_manager.get_all_logos()

        if not pending:
            flash('Brak zespołów do uzupełnienia', 'info')
            return redirect(url_for('list_teams'))

        return render_template('teams/pending.html', pending_teams=pending, logos=logos)

    @app.route('/api/teams/scraping/status')
    def api_teams_scrape_status():
        """API: Get scraping status"""
        status = team_scraper_manager.get_scraping_status()
        return jsonify(status)

    @app.route('/api/teams/stats')
    def api_stats():
        """API: Get team statistics"""
        return jsonify(team_scraper_manager.get_statistics())

    @app.route('/api/leagues/<int:league_id>/standings')
    @app.route('/api/leagues/<int:league_id>/standings/group/<int:group_nr>')
    def api_league_standings(league_id, group_nr=1):
        """Zwraca tabelę ligową w formacie JSON.

        Response:
            {
              "official": [...],   # tabela z meczów zakończonych
              "virtual":  [...],   # tabela z meczów zakończonych + live
              "has_live": bool
            }
        Każdy wiersz tabeli zawiera:
            team_id, team_name, team_short_name,
            games, points, wins, draws, loses,
            goals_scored, goals_lost, goal_difference
        """
        from flask import jsonify
        from app.models.game import Game
        from app.models.league import League

        league = League.query.get(league_id)
        if not league:
            return jsonify({'error': 'Nie znaleziono ligi'}), 404

        data = Game.get_league_tables(league_id, group_nr=group_nr)
        return jsonify(data)

    @app.route('/leagues/<int:league_id>/games/scrape')
    def scrape_games(league_id):
        """Start scraping games (MZPN HTML) for a league in background thread."""
        from flask import jsonify
        league = league_manager.get_league_by_id(league_id)
        if not league:
            return jsonify({'error': 'Nie znaleziono ligi'}), 404
        if not league.games_url:
            return jsonify({'error': 'Liga nie ma skonfigurowanego URL do scrapowania'}), 400
        if game_scraper_manager.is_scraping_in_progress():
            return jsonify({'error': 'Scrapowanie już trwa'}), 409
        try:
            game_scraper_manager.scrape_games_async([league.games_url], league_name=league.name)
            return jsonify({'status': 'started'}), 202
        except Exception as e:
            logger.error(f"Error starting scraping: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/leagues/<int:league_id>/games/scrape-superscore')
    def scrape_games_superscore(league_id):
        """Start scraping games from superscore.live API in background thread."""
        from flask import jsonify
        league = league_manager.get_league_by_id(league_id)
        if not league:
            return jsonify({'error': 'Nie znaleziono ligi'}), 404
        if not league.superscore_season_id:
            return jsonify({'error': 'Liga nie ma skonfigurowanego superscore_season_id'}), 400
        if game_scraper_manager.is_scraping_in_progress():
            return jsonify({'error': 'Scrapowanie już trwa'}), 409
        try:
            game_scraper_manager.scrape_superscore_async(
                [league.superscore_season_id], league_name=league.name
            )
            return jsonify({'status': 'started'}), 202
        except Exception as e:
            logger.error(f"Error starting superscore scraping: {e}")
            return jsonify({'error': str(e)}), 500
    

    @app.route('/game-setup')
    def game_setup():
        """Game setup page — manage periods, squads, referees, cameras."""
        from app.models.settings import Settings
        from app.models.game import Game
        from app.models.period import Period
        # from app.managers.game_player_manager import GamePlayerManager
        # from core.managers.game_referee_manager import GameRefereeManager
        # from core.managers.game_commentator_manager import GameCommentatorManager
        # from core.managers.game_camera_manager import GameCameraManager

        settings = Settings.get_settings()

        game     = None
        periods  = []
        shootout = None
        assigned = {
            'home_squad':   [],
            'away_squad':   [],
            'referees':     [],
            'commentators': [],
            'cameras':      [],
        }

        if settings.current_game_id:
            game = Game.query.get(settings.current_game_id)
            if game:
                periods  = Period.query.filter_by(game_id=game.id).all()
                shootout = game.shootout

                pg_mgr = GamePlayerManager()
                assigned['home_squad']   = pg_mgr.get_players_for_game(game.id, team_id=game.home_team_id)
                assigned['away_squad']   = pg_mgr.get_players_for_game(game.id, team_id=game.away_team_id)
                assigned['referees']     = GameRefereeManager().get_referees_for_game(game.id)
                assigned['commentators'] = GameCommentatorManager().get_commentators_for_game(game.id)
                assigned['cameras']      = GameCameraManager().get_cameras_for_game(game.id)

        in_frame = request.args.get('in_frame', '0') == '1'
        return render_template('game-setup.html',
                            game=game,
                            periods=periods,
                            shootout=shootout,
                            settings=settings,
                            assigned=assigned,
                            in_frame=in_frame)
    
    @app.route('/games/')
    def list_games():
        """List all games in database"""
        games = game_manager.get_all_games()
        stats = game_scraper_manager.get_statistics()
        scraping_status = game_scraper_manager.get_scraping_status()

        return render_template('games/list.html',
                               games=games,
                               stats=stats,
                               scraping_status=scraping_status)
    
    @app.route('/api/player-game/<int:pg_id>', methods=['PATCH'])
    def api_patch_game_player(pg_id):
        """Update GamePlayer snapshot fields (number, is_goalkeeper, is_captain).
        If is_captain=True, clears is_captain for all other GamePlayer rows of same team in same game."""
        from flask import jsonify, request as req
        from app.models.game_player import GamePlayer
    

        pg = GamePlayer.query.get(pg_id)
        if not pg:
            return jsonify({'error': 'Nie znaleziono rekordu'}), 404

        from app.models.player import Player
        player = Player.query.get(pg.player_id)

        data = req.get_json()
        try:
            if 'number' in data:
                val = data['number']
                pg.number = int(val) if val not in (None, '', 'null') else None
                if player:
                    player.number = pg.number
            if 'is_goalkeeper' in data:
                pg.is_goalkeeper = bool(data['is_goalkeeper'])
                if player:
                    player.is_goalkeeper = pg.is_goalkeeper
            if 'is_captain' in data:
                is_captain = bool(data['is_captain'])
                pg.is_captain = is_captain
                if player:
                    player.is_captain = is_captain
                if is_captain:
                    # Clear captain for others in same team/game (GamePlayer)
                    others = GamePlayer.query.filter(
                        GamePlayer.game_id == pg.game_id,
                        GamePlayer.team_id == pg.team_id,
                        GamePlayer.id != pg.id,
                    ).all()
                    for other in others:
                        other.is_captain = False
                    # Clear captain for others in same team (Player)
                    from app.models.player import Player as _P
                    other_players = _P.query.filter(
                        _P.team_id == pg.team_id,
                        _P.id != pg.player_id,
                    ).all()
                    for op in other_players:
                        op.is_captain = False
            db.session.commit()
            return jsonify({'ok': True, 'pg': {'id': pg.id, 'number': pg.number, 'is_goalkeeper': pg.is_goalkeeper, 'is_captain': pg.is_captain}})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400
        
    @app.route('/api/assign/<content_type>/save', methods=['POST'])
    def api_assign_save(content_type):
        """Save assignment changes from modal (bulk replace)."""
        from flask import jsonify, request as req
    
        from app.models.game import Game

        settings = Settings.get_settings()
        if not settings.current_game_id:
            return jsonify({'error': 'Brak wybranego meczu'}), 400

        game = Game.query.get(settings.current_game_id)
        if not game:
            return jsonify({'error': 'Nie znaleziono meczu'}), 404

        data = req.get_json()
        game_id = game.id

        try:
            # ── home_squad / away_squad ──────────────────────────────────────────
            if content_type in ('home-squad', 'away-squad'):
                # from app.managers.game_player_manager import GamePlayerManager  # garbarnia manager!
                from app.models.game_player import GamePlayer, ROLE_STARTER, ROLE_SUBSTITUTE
                team_id = game.home_team_id if content_type == 'home-squad' else game.away_team_id

                pg_mgr = GamePlayerManager()
                existing = GamePlayer.query.filter_by(game_id=game_id, team_id=team_id).all()
                for pg in existing:
                    db.session.delete(pg)
                db.session.commit()

                for item in data.get('starters', []):
                    pg_mgr.assign_player_to_game(item['player_id'], game_id, role=ROLE_STARTER)
                for item in data.get('substitutes', []):
                    pg_mgr.assign_player_to_game(item['player_id'], game_id, role=ROLE_SUBSTITUTE)
                return jsonify({'ok': True})

            # ── referees ─────────────────────────────────────────────────────────
            if content_type == 'referees':
                # from core.managers.game_referee_manager import GameRefereeManager
                from app.models.game_referee import GameReferee
            

                existing = GameReferee.query.filter_by(game_id=game_id).all()
                for gr in existing:
                    db.session.delete(gr)
                db.session.commit()

                gr_mgr = GameRefereeManager()
                for item in data.get('assigned', []):
                    gr_mgr.assign_referee_to_game(game_id, item['referee_id'], item['type'])
                return jsonify({'ok': True})

            # ── commentators ─────────────────────────────────────────────────────
            if content_type == 'commentators':
                # from core.managers.game_commentator_manager import GameCommentatorManager
                from app.models.game_commentator import GameCommentator
            

                existing = GameCommentator.query.filter_by(game_id=game_id).all()
                for gc in existing:
                    db.session.delete(gc)
                db.session.commit()

                gc_mgr = GameCommentatorManager()
                for item in data.get('assigned', []):
                    gc_mgr.assign_commentator_to_game(game_id, item['commentator_id'], item['type'])
                return jsonify({'ok': True})

            # ── cameras ───────────────────────────────────────────────────────────
            if content_type == 'cameras':
                # from core.managers.game_camera_manager import GameCameraManager
                from app.models.game_camera import GameCamera
            

                existing = GameCamera.query.filter_by(game_id=game_id).all()
                for gc in existing:
                    db.session.delete(gc)
                db.session.commit()

                gc_mgr = GameCameraManager()
                for item in data.get('assigned', []):
                    gc_mgr.assign_camera_to_game(
                        game_id=game_id,
                        camera_id=item['camera_id'],
                        hdmi_input=item['hdmi_input'],
                        location=item.get('location', ''),
                        is_motorized=item.get('is_motorized', False),
                    )
                return jsonify({'ok': True})

        except Exception as e:
            return jsonify({'error': str(e)}), 400

        return jsonify({'error': f'Nieznany typ: {content_type}'}), 400
    
    @app.route('/api/assign/uniforms/save', methods=['POST'])
    def api_uniforms_save():
        """Save selected uniform colors for both teams into the current game."""
        import json as _json
    
        from app.models.game import Game

        settings = Settings.get_settings()
        if not settings.current_game_id:
            return jsonify({'error': 'Brak wybranego meczu'}), 400

        game = Game.query.get(settings.current_game_id)
        if not game:
            return jsonify({'error': 'Nie znaleziono meczu'}), 404

        data = request.get_json()
        try:
            home_colors = data.get('home_colors')
            away_colors = data.get('away_colors')
            if home_colors is not None:
                game.home_team_uniform = _json.dumps(home_colors)
            if away_colors is not None:
                game.away_team_uniform = _json.dumps(away_colors)
            db.session.commit()
            return jsonify({'ok': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400
        
    @app.route('/api/games/scrape/status')
    def api_games_scrape_status():
        """API: Get current game scraping status"""
        # from app.managers.game_scraper_manager import GameScraperManager
        from flask import jsonify
        game_scraper_manager = GameScraperManager()
        status = game_scraper_manager.get_scraping_status()
        return jsonify(status)