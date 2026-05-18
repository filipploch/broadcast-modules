"""
app.routes.turniej — trasy specyficzne dla modułu turniej.
"""
from flask import (render_template, jsonify, current_app,
                   flash, redirect, url_for, request)
from core.extensions import db
from app.managers import (
    GameManager, LeagueManager, SeasonManager,
    GameEventManager, CameraManager, GameCameraManager,
    CommentatorManager, GameCommentatorManager,
    RefereeManager, GameRefereeManager,
    GamePlayerManager, PlayerManager,
    StadiumManager, EventManager,
)
from app.models.period import Period
from app.models.settings import Settings
import logging
import os

logger = logging.getLogger(__name__)

game_manager   = GameManager()
league_manager = LeagueManager()


# ── Playoff helpers ───────────────────────────────────────────────────────────

def _playoff_winner(game):
    """Winner team_id from a finished game; falls back to shootout if tied."""
    h, a = game.home_team_goals, game.away_team_goals
    if h is None or a is None:
        return None
    if h > a:
        return game.home_team_id
    if a > h:
        return game.away_team_id
    if game.shootout:
        return game.shootout.winner_id
    return None


def _playoff_loser(game):
    winner = _playoff_winner(game)
    if winner is None:
        return None
    return game.away_team_id if winner == game.home_team_id else game.home_team_id


def _make_game(gm, kl, st_id, row_home, row_away, rnd, grp):
    return gm.create_game(
        home_team_id=row_home['team_id'],
        away_team_id=row_away['team_id'],
        league_id=kl.id,
        stadium_id=st_id,
        round_number=rnd,
        group_nr=grp,
    )


def _make_game_by_id(gm, kl, st_id, home_id, away_id, rnd, grp):
    return gm.create_game(
        home_team_id=home_id,
        away_team_id=away_id,
        league_id=kl.id,
        stadium_id=st_id,
        round_number=rnd,
        group_nr=grp,
    )


def register_routes(app):
    """Rejestruje trasy specyficzne dla turniej."""

    from flask import render_template, jsonify, current_app, flash, redirect, url_for, request

    from app.models.team import Team

    import logging
    from datetime import datetime
    import os

    logger = logging.getLogger(__name__)

    # ── Assign API ────────────────────────────────────────────────────────────

    @app.route('/api/assign/<content_type>/data')
    def api_assign_data(content_type):
        from app.models.game import Game
        from app.models.game_camera import VALID_HDMI_INPUTS, HDMI_DEFAULT_LOCATION
        from app.models.player import Player

        settings = Settings.get_settings()
        if not settings.current_game_id:
            return jsonify({'error': 'Brak wybranego meczu'}), 400

        game = Game.query.get(settings.current_game_id)
        if not game:
            return jsonify({'error': 'Nie znaleziono meczu'}), 404

        game_id = game.id

        if content_type in ('home-squad', 'away-squad'):
            team_id = game.home_team_id if content_type == 'home-squad' else game.away_team_id
            team = game.home_team if content_type == 'home-squad' else game.away_team

            pg_mgr = GamePlayerManager()
            assigned_pgs = pg_mgr.get_players_for_game(game_id, team_id=team_id)
            assigned_ids = {pg.player_id for pg in assigned_pgs}

            assigned = [{
                'pg_id': pg.id,
                'player_id': pg.player_id,
                'label': f"{pg.player.last_name} {pg.player.first_name}",
                'last_name': pg.player.last_name,
                'first_name': pg.player.first_name,
                'number': pg.number,
                'is_captain': pg.is_captain,
                'is_goalkeeper': pg.is_goalkeeper,
            } for pg in assigned_pgs]

            all_players = (Player.query
                .filter_by(team_id=team_id)
                .order_by(Player.is_goalkeeper.desc(), Player.last_name.asc())
                .all())
            available = [{
                'player_id': p.id,
                'label': f"{p.last_name} {p.first_name}",
                'is_goalkeeper': p.is_goalkeeper,
            } for p in all_players if p.id not in assigned_ids]

            return jsonify({
                'title': f"Skład: {team.name}",
                'content_type': content_type,
                'team_id': team_id,
                'assigned': assigned,
                'available': available,
            })

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

    # ── Teams ─────────────────────────────────────────────────────────────────

    @app.route('/teams/<int:team_id>')
    def view_team(team_id):
        from core.managers.team_manager import TeamManager
        team = TeamManager().get_team_by_id(team_id)
        if not team:
            flash('Nie znaleziono zespołu', 'error')
            return redirect(url_for('list_teams'))
        return render_template('teams/view.html', team=team)

    @app.route('/teams/')
    def list_teams():
        from core.managers.team_manager import TeamManager
        teams = TeamManager().get_all_teams()
        return render_template('teams/list.html',
                               teams=teams,
                               stats={'total_teams': len(teams), 'pending_teams': 0},
                               scraping_status={})

    @app.route('/teams/scrape')
    def scrape_teams():
        flash('Scrapowanie nie jest dostępne w tym module', 'warning')
        return redirect(url_for('list_teams'))

    # ── Standings API ─────────────────────────────────────────────────────────

    @app.route('/api/leagues/<int:league_id>/standings')
    @app.route('/api/leagues/<int:league_id>/standings/group/<int:group_nr>')
    def api_league_standings(league_id, group_nr=None):
        from app.models.game import Game
        from app.models.league import League

        league = League.query.get(league_id)
        if not league:
            return jsonify({'error': 'Nie znaleziono ligi'}), 404

        if group_nr is None:
            group_nr = request.args.get('group_nr', type=int)
        if group_nr is None:
            max_group = (
                db.session.query(db.func.max(Game.group_nr))
                .filter(Game.league_id == league_id)
                .scalar()
            )
            group_nr = max_group or 1

        data = Game.get_league_tables(league_id, group_nr=group_nr)
        data['group_nr'] = group_nr
        return jsonify(data)

    # ── Game setup ────────────────────────────────────────────────────────────

    @app.route('/game-setup')
    def game_setup():
        from app.models.settings import Settings
        from app.models.game import Game
        from app.models.period import Period

        settings = Settings.get_settings()

        game    = None
        periods = []
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
                periods = Period.query.filter_by(game_id=game.id).all()

                pg_mgr = GamePlayerManager()
                assigned['home_squad']   = pg_mgr.get_players_for_game(game.id, team_id=game.home_team_id)
                assigned['away_squad']   = pg_mgr.get_players_for_game(game.id, team_id=game.away_team_id)
                assigned['referees']     = GameRefereeManager().get_referees_for_game(game.id)
                assigned['commentators'] = GameCommentatorManager().get_commentators_for_game(game.id)
                assigned['cameras']      = GameCameraManager().get_cameras_for_game(game.id)

        return render_template('game-setup.html',
                               game=game,
                               periods=periods,
                               shootout=None,
                               settings=settings,
                               assigned=assigned)

    # ── prepare-broadcast override (turniej: 15 min, count-up) ───────────────
    # routes_crud already registered this route; we replace the view function.

    def _prepare_game_for_broadcast(game_id):
        from app.managers.period_manager import PeriodManager

        game = game_manager.get_game_by_id(game_id)
        if not game:
            flash('Nie znaleziono meczu', 'error')
            return redirect(url_for('list_games'))

        if game.periods.count() > 0:
            flash('Mecz ma już utworzone okresy', 'warning')
            return redirect(url_for('game_period_choice'))

        camera_manager = CameraManager()
        main_camera = camera_manager.get_camera_by_id(1)
        if main_camera:
            GameCameraManager().assign_camera_to_game(
                game_id=game.id, camera_id=main_camera.id, hdmi_input=1, location='Główna'
            )

        period_manager = PeriodManager()
        try:
            periods = period_manager.create_default_periods(game_id=game_id)
            flash(f'Utworzono {len(periods)} okres(y) dla meczu. Mecz gotowy do transmisji.', 'success')
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Error preparing game for broadcast: {e}")
            flash(f'Błąd podczas przygotowania meczu: {str(e)}', 'error')

        return redirect(url_for('edit_game', game_id=game_id))

    app.view_functions['prepare_game_for_broadcast'] = _prepare_game_for_broadcast

    # ── Shootout (faza pucharowa) ─────────────────────────────────────────────

    def _add_shootout(game_id):
        from core.managers.shootout_manager import ShootoutManager
        game = game_manager.get_game_by_id(game_id)
        if not game:
            flash('Nie znaleziono meczu', 'error')
            return redirect(url_for('list_games'))
        if game.shootout:
            flash('Rzuty karne już dodane do tego meczu', 'warning')
            return redirect(url_for('edit_game', game_id=game_id))
        try:
            ShootoutManager().create_shootout(game_id=game_id)
            flash('Dodano konkurs rzutów karnych', 'success')
        except Exception as e:
            flash(f'Błąd: {e}', 'error')
        return redirect(url_for('edit_game', game_id=game_id))

    app.view_functions['add_shootout'] = _add_shootout

    # ── League create/edit — bez pól URL scraperów ────────────────────────────

    def _create_league(season_id=None):
        from core.managers.season_manager import SeasonManager
        seasons = SeasonManager().get_all_seasons()
        if request.method == 'POST':
            try:
                selected_season_id = int(request.form.get('season_id', season_id or 0))
                league = league_manager.create_league(
                    season_id=selected_season_id,
                    name=request.form['name'],
                    allows_draw=('allows_draw' in request.form),
                )
                flash(f'Utworzono ligę: {league.name}', 'success')
                return redirect(url_for('view_league', league_id=league.id))
            except ValueError as e:
                flash(str(e), 'error')
            except Exception as e:
                logger.error(f"Error creating league: {e}")
                flash(f'Błąd podczas tworzenia ligi: {str(e)}', 'error')
        return render_template('turniej/leagues/create.html',
                               seasons=seasons,
                               selected_season_id=season_id)

    app.view_functions['create_league'] = _create_league

    # ── Team create — bez URL scraperów ──────────────────────────────────────

    def _create_team():
        from core.managers.team_manager import TeamManager
        logos = TeamManager().get_all_logos()
        if request.method == 'POST':
            try:
                uniform_home = request.form.getlist('uniform_home[]')
                uniform_away = request.form.getlist('uniform_away[]')
                team = TeamManager().create_team(
                    name=request.form['name'],
                    name_14=request.form['name_14'],
                    short_name=request.form['short_name'],
                    logo_path=request.form.get('logo_path', 'static/images/logos/default.png'),
                    uniform={'home': uniform_home, 'away': uniform_away},
                )
                flash(f'Dodano zespół: {team.name}', 'success')
                return redirect(url_for('view_team', team_id=team.id))
            except Exception as e:
                logger.error(f"Error creating team: {e}")
                flash(f'Błąd podczas tworzenia zespołu: {str(e)}', 'error')
        return render_template('turniej/teams/create.html', logos=logos)

    app.view_functions['create_team'] = _create_team

    # ── Games list ────────────────────────────────────────────────────────────

    @app.route('/games/')
    def list_games():
        games = game_manager.get_all_games()
        return render_template('games/list.html',
                               games=games,
                               stats={},
                               scraping_status={})

    # ── GamePlayer PATCH ──────────────────────────────────────────────────────

    @app.route('/api/player-game/<int:pg_id>', methods=['PATCH'])
    def api_patch_game_player(pg_id):
        from app.models.game_player import GamePlayer

        pg = GamePlayer.query.get(pg_id)
        if not pg:
            return jsonify({'error': 'Nie znaleziono rekordu'}), 404

        from app.models.player import Player
        player = Player.query.get(pg.player_id)

        data = request.get_json()
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
                    others = GamePlayer.query.filter(
                        GamePlayer.game_id == pg.game_id,
                        GamePlayer.team_id == pg.team_id,
                        GamePlayer.id != pg.id,
                    ).all()
                    for other in others:
                        other.is_captain = False
                    other_players = Player.query.filter(
                        Player.team_id == pg.team_id,
                        Player.id != pg.player_id,
                    ).all()
                    for op in other_players:
                        op.is_captain = False
            db.session.commit()
            return jsonify({'ok': True, 'pg': {
                'id': pg.id, 'number': pg.number,
                'is_goalkeeper': pg.is_goalkeeper, 'is_captain': pg.is_captain,
            }})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

    # ── Assign save ───────────────────────────────────────────────────────────

    @app.route('/api/assign/<content_type>/save', methods=['POST'])
    def api_assign_save(content_type):
        from app.models.game import Game

        settings = Settings.get_settings()
        if not settings.current_game_id:
            return jsonify({'error': 'Brak wybranego meczu'}), 400

        game = Game.query.get(settings.current_game_id)
        if not game:
            return jsonify({'error': 'Nie znaleziono meczu'}), 404

        data = request.get_json()
        game_id = game.id

        try:
            if content_type in ('home-squad', 'away-squad'):
                from app.models.game_player import GamePlayer
                team_id = game.home_team_id if content_type == 'home-squad' else game.away_team_id
                pg_mgr = GamePlayerManager()
                existing = GamePlayer.query.filter_by(game_id=game_id, team_id=team_id).all()
                for pg in existing:
                    db.session.delete(pg)
                db.session.commit()
                for item in data.get('assigned', []):
                    pg_mgr.assign_player_to_game(item['player_id'], game_id)
                return jsonify({'ok': True})

            if content_type == 'referees':
                from app.models.game_referee import GameReferee
                existing = GameReferee.query.filter_by(game_id=game_id).all()
                for gr in existing:
                    db.session.delete(gr)
                db.session.commit()
                gr_mgr = GameRefereeManager()
                for item in data.get('assigned', []):
                    gr_mgr.assign_referee_to_game(game_id, item['referee_id'], item['type'])
                return jsonify({'ok': True})

            if content_type == 'commentators':
                from app.models.game_commentator import GameCommentator
                existing = GameCommentator.query.filter_by(game_id=game_id).all()
                for gc in existing:
                    db.session.delete(gc)
                db.session.commit()
                gc_mgr = GameCommentatorManager()
                for item in data.get('assigned', []):
                    gc_mgr.assign_commentator_to_game(game_id, item['commentator_id'], item['type'])
                return jsonify({'ok': True})

            if content_type == 'cameras':
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

    # ── Playoff Generator ─────────────────────────────────────────────────────

    @app.route('/leagues/<int:league_id>/playoff-generator', methods=['GET', 'POST'])
    def playoff_generator(league_id):
        from app.models.league import League
        from app.models.game import Game
        from app.models.stadium import Stadium
        from core.managers.game_manager import GameManager as CoreGM

        league = League.query.get_or_404(league_id)
        all_leagues = League.query.filter(League.id != league_id).order_by(League.name).all()
        stadiums = Stadium.query.order_by(Stadium.name).all()

        standings_a = Game.calculate_league_table(league_id, group_nr=1, include_pending=False)
        standings_b = Game.calculate_league_table(league_id, group_nr=2, include_pending=False)

        knockout_league_id = request.args.get('kl', type=int) or request.form.get('knockout_league_id', type=int)
        knockout_league = League.query.get(knockout_league_id) if knockout_league_id else None

        round1_games, round2_games = [], []
        can_gen_r1 = can_gen_r2 = False

        if knockout_league:
            round1_games = (Game.query
                .filter_by(league_id=knockout_league_id, round=1)
                .order_by(Game.group_nr).all())
            round2_games = (Game.query
                .filter_by(league_id=knockout_league_id, round=2)
                .order_by(Game.group_nr).all())

            can_gen_r1 = (not round1_games
                          and len(standings_a) >= 4
                          and len(standings_b) >= 4)

            if not round2_games:
                sf_a = next((g for g in round1_games if g.group_nr == 1), None)
                sf_b = next((g for g in round1_games if g.group_nr == 2), None)
                if sf_a and sf_b:
                    can_gen_r2 = (sf_a.status == Game.STATUS_FINISHED
                                  and sf_b.status == Game.STATUS_FINISHED
                                  and _playoff_winner(sf_a) is not None
                                  and _playoff_winner(sf_b) is not None)

        if request.method == 'POST':
            action = request.form.get('action')
            kl_id  = request.form.get('knockout_league_id', type=int)
            st_id  = request.form.get('stadium_id', type=int)
            kl     = League.query.get(kl_id) if kl_id else None

            if not kl:
                flash('Wybierz ligę pucharową', 'error')
            elif action == 'round1':
                try:
                    gm = CoreGM()
                    _make_game(gm, kl, st_id, standings_a[0], standings_b[1], rnd=1, grp=1)
                    _make_game(gm, kl, st_id, standings_b[0], standings_a[1], rnd=1, grp=2)
                    _make_game(gm, kl, st_id, standings_a[2], standings_b[2], rnd=1, grp=3)
                    _make_game(gm, kl, st_id, standings_a[3], standings_b[3], rnd=1, grp=4)
                    flash('Wygenerowano mecze I rundy (półfinały + o 5. i 7. miejsce)', 'success')
                except Exception as e:
                    flash(f'Błąd: {e}', 'error')

            elif action == 'finals':
                sf_a = Game.query.filter_by(league_id=kl_id, round=1, group_nr=1).first()
                sf_b = Game.query.filter_by(league_id=kl_id, round=1, group_nr=2).first()
                if not sf_a or not sf_b:
                    flash('Brak meczów półfinałowych', 'error')
                else:
                    w_a, l_a = _playoff_winner(sf_a), _playoff_loser(sf_a)
                    w_b, l_b = _playoff_winner(sf_b), _playoff_loser(sf_b)
                    if not all([w_a, l_a, w_b, l_b]):
                        flash('Nie można ustalić wyników półfinałów — sprawdź wyniki lub dodaj rzuty karne', 'error')
                    else:
                        try:
                            gm = CoreGM()
                            _make_game_by_id(gm, kl, st_id, w_a, w_b, rnd=2, grp=1)
                            _make_game_by_id(gm, kl, st_id, l_a, l_b, rnd=2, grp=2)
                            flash('Wygenerowano finał i mecz o 3. miejsce', 'success')
                        except Exception as e:
                            flash(f'Błąd: {e}', 'error')

            return redirect(url_for('playoff_generator', league_id=league_id,
                                    kl=kl_id or knockout_league_id))

        return render_template(
            'turniej/leagues/playoff_generator.html',
            league=league,
            all_leagues=all_leagues,
            stadiums=stadiums,
            standings_a=standings_a,
            standings_b=standings_b,
            knockout_league=knockout_league,
            knockout_league_id=knockout_league_id,
            round1_games=round1_games,
            round2_games=round2_games,
            can_gen_r1=can_gen_r1,
            can_gen_r2=can_gen_r2,
        )
