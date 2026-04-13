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
    CommentatorManager, GameCommentatorManager,
    RefereeManager, GameRefereeManager,
    GamePlayerManager, PlayerManager,
    StadiumManager, EventManager,
)
from app.managers.game_scraper_manager import GameScraperManager
from app.managers.team_scraper_manager import TeamScraperManager
from app.managers.player_scraper_manager import PlayerScraperManager
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
    from app import routes_crud  # noqa: F401


    logger = logging.getLogger(__name__)

    team_manager = TeamManager()
    team_scraper_manager = TeamScraperManager()
    player_scraper_manager = PlayerScraperManager()
    # game_manager = GameManager()
    game_scraper_manager = GameScraperManager()
    # league_manager = LeagueManager()

    @app.route('/ui')
    def ui_dashboard():
        """
        Main UI dashboard with Jinja2 rendering
    
        Renders timers server-side from Settings.current_timers
        JavaScript only handles WebSocket updates, not timer creation
        """
    
    
        from app.models.game import Game
        from app.models.team import Team
    
        settings = Settings.get_settings()
        current_period_id = settings.current_period_id
    
        # Get current period
        period = None
        game = None
        if current_period_id:
            period = Period.query.filter_by(id=current_period_id).first()
            if period:
                game = Game.query.get(period.game_id)
                teams = {
                    'home': Team.query.get(game.home_team_id),
                    'away': Team.query.get(game.away_team_id)
                }
    
            # Get current timers from Settings
            current_timers = settings.get_current_timers()
            main_timer = current_timers.get('main')
            home_penalties = current_timers.get('penalties')['home']
            away_penalties = current_timers.get('penalties')['away']
            penalties = home_penalties + away_penalties
        
            # Log for debugging
            current_app.logger.info(f"UI Dashboard - Period: {period.id if period else None}")
            current_app.logger.info(f"Main timer: {main_timer.get('timer_id') if main_timer else None}")
            current_app.logger.info(f"Penalties: {len(penalties)}")
        
            return render_template('ui-jinja.html',
                                period=period,
                                game=game,
                                main_timer=main_timer,
                                teams=teams,
                                penalties=penalties)
        else:
            current_game_id = settings.current_game_id
        
            game = Game.query.get(current_game_id)
            teams = {
                'home': Team.query.get(game.home_team_id),
                'away': Team.query.get(game.away_team_id)
            }

            return render_template('ui-shootout.html')


    @app.route('/')
    def index():
        """
        Period-control page — timer + scoreboard only.
        Standalone UI for the operator running the clock during a match.
        Mirrors the ui_dashboard data-loading logic but renders index.html.
        """
    
    
        from app.models.game import Game
        from app.models.team import Team

        settings = Settings.get_settings()
        current_period_id = settings.current_period_id

        period = None
        game   = None
        teams  = {'home': None, 'away': None}
        main_timer = None

        if current_period_id:
            period = Period.query.filter_by(id=current_period_id).first()
            if period:
                game = Game.query.get(period.game_id)
                if game:
                    teams = {
                        'home': Team.query.get(game.home_team_id),
                        'away': Team.query.get(game.away_team_id),
                    }

            current_timers = settings.get_current_timers()
            main_timer = current_timers.get('main')

        return render_template('index.html',
                               period=period,
                               game=game,
                               main_timer=main_timer,
                               teams=teams)


    @app.route('/game-setup')
    def game_setup():
        """Game setup page — manage periods, squads, referees, cameras."""
    
        from app.models.game import Game
    
        from core.managers.game_player_manager import GamePlayerManager
        from core.managers.game_referee_manager import GameRefereeManager
        from core.managers.game_commentator_manager import GameCommentatorManager
        from core.managers.game_camera_manager import GameCameraManager

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

        return render_template('game-setup.html',
                               game=game,
                               periods=periods,
                               shootout=shootout,
                               settings=settings,
                               assigned=assigned)



    @app.route('/game-period-choice')
    def game_period_choice():
        """Period selection page — start, finish, reset periods and shootout."""
    
        from app.models.game import Game
    

        settings = Settings.get_settings()

        game     = None
        periods  = []
        penalty  = None

        if settings.current_game_id:
            game = Game.query.get(settings.current_game_id)
            if game:
                periods = Period.query.filter_by(game_id=game.id).all()
                penalty = game.shootout

        return render_template('game-period-choice.html',
                               game=game,
                               periods=periods,
                               penalty=penalty,
                               settings=settings)

    @app.route('/period/<int:period_id>/start')
    def start_period(period_id):
        """Start a period and redirect to UI dashboard"""
        from core.managers.period_manager import PeriodManager
    
        from app.models.game import Game
        from core.managers import get_timer_manager

        period_manager = PeriodManager()
        period = period_manager.get_period_by_id(period_id)

        if not period:
            flash('Nie znaleziono okresu', 'error')
            return redirect(url_for('game_period_choice'))

        # Check if this period can be started
        game = Game.query.get(period.game_id)
        if not game:
            flash('Nie znaleziono meczu', 'error')
            return redirect(url_for('game_period_choice'))

        # Check if previous period is finished (if not first period)
        if period.period_order > 1:
            previous_periods = Period.query.filter_by(
                game_id=period.game_id
            ).filter(
                Period.period_order < period.period_order
            ).all()

            for prev_period in previous_periods:
                if prev_period.status != Period.STATUS_FINISHED:
                    flash(f'Nie można rozpocząć {period.description}. Poprzedni okres nie został zakończony.', 'error')
                    return redirect(url_for('game_period_choice'))

        try:
            # WAŻNA KOLEJNOŚĆ:
            # 1. Najpierw usuń poprzedni timer (jeśli istnieje)
            timer_manager = get_timer_manager()
            current_timers = Settings.get_current_timers()
            previous_main = current_timers.get('main')
            if previous_main and previous_main.get('timer_id'):
                timer_manager.remove_timer(previous_main['timer_id'])

            # 2. Ustaw current_period_id w Settings PRZED start_period,
            #    żeby on_timer_created() mógł odczytać prawidłowy period_id
            #    przy potwierdzeniu z pluginu (unikamy race condition: period_id=None).
            Settings.set_current_period(period_id)

            # 3. Teraz uruchom okres — create_timer wysyła wiadomość do pluginu
            period_manager.start_period(period_id)

            # 4. Jeśli to pierwsza część, ustaw mecz jako trwający
            if period.period_order == 1:
                game.set_live()
                db.session.commit()

            flash(f'Rozpoczęto {period.description}', 'success')
            from core.extensions import socketio
            socketio.emit('reload_ui_dashboard')
            return redirect(url_for('index'))

        except Exception as e:
            logger.error(f"Error starting period: {e}")
            flash(f'Błąd podczas rozpoczynania okresu: {str(e)}', 'error')
            return redirect(url_for('game_period_choice'))


    @app.route('/period/<int:period_id>/finish')
    def finish_period(period_id):
        """Finish a period and return to broadcast control"""
        from core.managers.period_manager import PeriodManager
    
        from app.models.game import Game
    
        period_manager = PeriodManager()
        period = period_manager.get_period_by_id(period_id)
    
        if not period:
            flash('Nie znaleziono okresu', 'error')
            return redirect(url_for('game_period_choice'))
    
        try:
            # Finish the period
            period_manager.finish_period(period_id)
        
            # Clear actual period in settings
            Settings.set_current_period(None)
        
            # Check if this was the last period
            game = Game.query.get(period.game_id)
            if game:
                all_periods = game.get_periods_list()
                all_finished = all(p.status == Period.STATUS_FINISHED for p in all_periods)
            
                if all_finished:
                    # All periods finished - finish the game
                    game.set_finished()
                    db.session.commit()
                    flash(f'Zakończono {period.description}. Mecz zakończony!', 'success')
                else:
                    flash(f'Zakończono {period.description}', 'success')
        
            return redirect(url_for('game_period_choice'))
        
        except Exception as e:
            logger.error(f"Error finishing period: {e}")
            flash(f'Błąd podczas kończenia okresu: {str(e)}', 'error')
            return redirect(url_for('game_period_choice'))


    @app.route('/period/<int:period_id>/reset-status')
    def reset_period_status(period_id):
        """Reset period status to NOT_STARTED (for error correction)"""
        from core.managers.period_manager import PeriodManager
    
        period_manager = PeriodManager()
        period = period_manager.get_period_by_id(period_id)
    
        if not period:
            flash('Nie znaleziono okresu', 'error')
            return redirect(url_for('game_period_choice'))
    
        try:
            period_manager.set_period_status(period_id, Period.STATUS_NOT_STARTED)
            flash(f'Zresetowano status okresu: {period.description}', 'success')
        except Exception as e:
            logger.error(f"Error resetting period status: {e}")
            flash(f'Błąd podczas resetowania statusu: {str(e)}', 'error')
    
        return redirect(url_for('game_period_choice'))


    @app.route('/game/<int:game_id>/shootout/start')
    def start_shootout(game_id):
        """
        Rozpocznij konkurs rzutów karnych:
        1. Utwórz rekord Shootout (jeśli nie istnieje).
        2. Ustaw current_shootout_id w Settings.
        3. Przekieruj do UI dashboard.
        """
        from app.managers.shootout_manager import ShootoutManager
    
        from app.models.game import Game
    

        game = Game.query.get(game_id)
        if not game:
            flash('Nie znaleziono meczu', 'error')
            return redirect(url_for('game_period_choice'))

        # Walidacja: liga musi nie dopuszczać remisu
        if game.league and game.league.allows_draw:
            flash('Ta liga dopuszcza remis — konkurs rzutów karnych niedostępny.', 'error')
            return redirect(url_for('game_period_choice'))

        # Walidacja: wszystkie okresy muszą być zakończone
        periods = game.get_periods_list()
        if not periods or not all(p.status == Period.STATUS_FINISHED for p in periods):
            flash('Wszystkie okresy meczu muszą być zakończone przed konkursem rzutów karnych.', 'error')
            return redirect(url_for('game_period_choice'))

        # Walidacja: wynik musi być remisowy
        if game.home_team_goals != game.away_team_goals:
            flash('Konkurs rzutów karnych jest dostępny tylko przy remisie po regulaminowym czasie gry.', 'error')
            return redirect(url_for('game_period_choice'))

        shootout_manager = ShootoutManager()

        try:
            # Utwórz rekord Shootout jeśli jeszcze nie istnieje
            if not game.shootout:
                shootout_manager.create_shootout(game_id=game_id)
                # Odśwież obiekt żeby załadować nową relację
                db.session.refresh(game)

            # Ustaw jako aktywny konkurs w Settings
            Settings.set_current_shootout(game.shootout.id)

            flash('Rozpoczęto konkurs rzutów karnych.', 'success')
            from core.extensions import socketio
            socketio.emit('reload_ui_dashboard')
            return redirect(url_for('index'))

        except Exception as e:
            logger.error(f"Error starting penalty shootout: {e}")
            flash(f'Błąd podczas rozpoczynania konkursu: {str(e)}', 'error')
            return redirect(url_for('game_period_choice'))


    @app.route('/game/<int:game_id>/shootout/reset')
    def reset_shootout(game_id):
        """Reset shootout — delete record and clear current_shootout_id in Settings."""
    
        from app.models.game import Game
        from app.managers.shootout_manager import ShootoutManager

        game = Game.query.get(game_id)
        if not game:
            flash('Nie znaleziono meczu', 'error')
            return redirect(url_for('game_period_choice'))

        try:
            shootout_manager = ShootoutManager()
            if game.shootout:
                shootout_manager.delete_shootout(game.shootout.id)
            Settings.set_current_shootout(None)
            flash('Zresetowano konkurs rzutów karnych', 'success')
        except Exception as e:
            logger.error(f"Error resetting shootout: {e}")
            flash(f'Błąd podczas resetowania konkursu: {str(e)}', 'error')

        return redirect(url_for('game_period_choice'))

    @app.route('/game/<int:game_id>/shootout/finish')
    def finish_shootout(game_id):
        """Zakończ konkurs rzutów karnych i wróć do panelu."""
    
        from app.models.game import Game

        game = Game.query.get(game_id)
        if not game:
            flash('Nie znaleziono meczu', 'error')
            return redirect(url_for('game_period_choice'))

        try:
            Settings.set_current_shootout(None)
            game.set_finished()
            db.session.commit()
            flash('Zakończono konkurs rzutów karnych.', 'success')
        except Exception as e:
            logger.error(f"Error finishing penalty shootout: {e}")
            flash(f'Błąd: {str(e)}', 'error')

        return redirect(url_for('game_period_choice'))


    # @app.route('/api/status')
    # def api_status():
    #     """Application status"""
    #     return jsonify({
    #         'status': 'running',
    #         'module_id': current_app.config['MODULE_ID']
    #     })

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

    @app.route('/common-data/')
    def common_data():
 
        return render_template('common-data.html')

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


    @app.route('/teams/create', methods=['GET', 'POST'])
    def create_team():
        """Create new team manually (without scraping)"""
        if request.method == 'POST':
            try:
                uniform_home = request.form.getlist('uniform_home[]')
                uniform_away = request.form.getlist('uniform_away[]')
                team = team_manager.create_team(
                    name=request.form['name'],
                    name_14=request.form['name_14'],
                    short_name=request.form['short_name'],
                    # team_url=request.form['team_url'],
                    logo_path=request.form.get('logo_path', 'static/images/logos/default.png'),
                    uniform={'home': uniform_home, 'away': uniform_away}
                )

                flash(f'Dodano zespół: {team.name}', 'success')
                return redirect(url_for('view_team', team_id=team.id))

            except Exception as e:
                logger.error(f"Error creating team: {e}")
                flash(f'Błąd podczas tworzenia zespołu: {str(e)}', 'error')

        return render_template('teams/create.html')


    @app.route('/teams/<int:team_id>/edit', methods=['GET', 'POST'])
    def edit_team(team_id):
        """Edit existing team"""
        team = team_manager.get_team_by_id(team_id)
        logos = team_manager.get_all_logos()

        if not team:
            flash('Nie znaleziono zespołu', 'error')
            return redirect(url_for('list_teams'))

        if request.method == 'POST':
            try:
                uniform_home = request.form.getlist('uniform_home[]')
                uniform_away = request.form.getlist('uniform_away[]')
                team_manager.update_team(
                    team_id=team_id,
                    name=request.form.get('name'),
                    name_14=request.form.get('name_14'),
                    short_name=request.form.get('short_name'),
                    # team_url=request.form.get('team_url'),
                    logo_path=request.form.get('logo_path'),
                    uniform={'home': uniform_home, 'away': uniform_away}
                )

                flash(f'Zaktualizowano zespół: {team.name}', 'success')
                return redirect(url_for('view_team', team_id=team.id))

            except Exception as e:
                logger.error(f"Error updating team: {e}")
                flash(f'Błąd podczas aktualizacji zespołu: {str(e)}', 'error')

        return render_template('teams/edit.html', team=team, logos=logos)


    @app.route('/teams/<int:team_id>/delete', methods=['POST'])
    def delete_team(team_id):
        """Delete team"""
        team = team_manager.get_team_by_id(team_id)

        if not team:
            flash('Nie znaleziono zespołu', 'error')
            return redirect(url_for('list_teams'))

        team_name = team.name

        if team_manager.delete_team(team_id):
            flash(f'Usunięto zespół: {team_name}', 'success')
        else:
            flash('Błąd podczas usuwania zespołu', 'error')

        return redirect(url_for('list_teams'))


    # =========================
    # Scraping Workflow (Async)
    # =========================

    @app.route('/leagues/<int:league_id>/games/scrape')
    def scrape_games(league_id):
        """Start scraping games for a league in background thread, return JSON"""
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

    @app.route('/teams/scrape', methods=['GET', 'POST'])
    def scrape_teams():
        """Start scraping teams in background thread, return JSON"""
        from flask import jsonify
        if team_scraper_manager.is_scraping_in_progress():
            return jsonify({'error': 'Scrapowanie już trwa'}), 409

        urls = [
            'https://nalffutsal.pl/?page_id=16',
            'https://nalffutsal.pl/?page_id=36',
        ]

        try:
            team_scraper_manager.scrape_leagues_async(urls, league_name='Zespoły NALF')
            return jsonify({'status': 'started'}), 202
        except Exception as e:
            logger.error(f"Error starting team scraping: {e}")
            return jsonify({'error': str(e)}), 500


    @app.route('/teams/pending')
    def pending_teams():
        """List pending teams from scraping that need completion"""
        pending = team_scraper_manager.get_pending_teams()
        logos = team_manager.get_all_logos()

        if not pending:
            flash('Brak zespołów do uzupełnienia', 'info')
            return redirect(url_for('list_teams'))

        return render_template('teams/pending.html', pending_teams=pending, logos=logos)


    @app.route('/teams/complete/<path:team_url>', methods=['GET', 'POST'])
    def complete_team(team_url):
        """Complete scraped team with additional data"""
        # Get pending team
        pending_team = team_scraper_manager.get_pending_team_by_url(team_url)
        logos = team_manager.get_all_logos()

        if not pending_team:
            flash('Nie znaleziono zespołu do uzupełnienia', 'error')
            return redirect(url_for('pending_teams'))

        if request.method == 'POST':
            try:
                team = team_scraper_manager.complete_team_from_scraping(
                    team_url=team_url,
                    name_14=request.form['name_14'],
                    short_name=request.form['short_name'],
                    logo_path=request.form.get('logo_path', 'static/images/logos/default.png')
                )

                if team:
                    flash(f'Dodano zespół: {team.name}', 'success')

                    # Check if there are more pending teams
                    remaining = len(team_scraper_manager.get_pending_teams())
                    if remaining > 0:
                        flash(f'Pozostało jeszcze {remaining} zespołów do uzupełnienia', 'info')
                        return redirect(url_for('pending_teams'))
                    else:
                        return redirect(url_for('list_teams'))
                else:
                    flash('Błąd podczas dodawania zespołu', 'error')

            except Exception as e:
                logger.error(f"Error completing team: {e}")
                flash(f'Błąd podczas dodawania zespołu: {str(e)}', 'error')

        return render_template('teams/complete.html', team=pending_team, logos=logos)


    @app.route('/teams/pending/clear', methods=['POST'])
    def clear_pending():
        """Clear all pending teams"""
        team_scraper_manager.clear_pending_teams()
        flash('Wyczyszczono listę zespołów do uzupełnienia', 'info')
        return redirect(url_for('list_teams'))


    # =========================
    # API Endpoints
    # =========================

    @app.route('/api/teams')
    def api_list_teams():
        """API: List all teams"""
        teams = team_manager.get_all_teams()
        return jsonify({
            'teams': [team.to_dict() for team in teams]
        })


    @app.route('/api/teams/<int:team_id>')
    def api_get_team(team_id):
        """API: Get single team"""
        team = team_manager.get_team_by_id(team_id)

        if not team:
            return jsonify({'error': 'Team not found'}), 404

        return jsonify(team.to_dict())


    @app.route('/api/teams/stats')
    def api_stats():
        """API: Get team statistics"""
        return jsonify(team_scraper_manager.get_statistics())


    @app.route('/api/teams/scraping/status')
    def api_teams_scrape_status():
        """API: Get scraping status"""
        status = team_scraper_manager.get_scraping_status()
        return jsonify(status)


    @app.route('/teams/scraping/stop', methods=['POST'])
    def stop_scraping():
        if team_scraper_manager.stop_scraping():
            return jsonify({'success': True, 'message': 'Stop requested'})
        return jsonify({'success': False, 'message': 'No scraping in progress'})

    """
    API Endpoint to add to routes.py
    Place this at the end of the API endpoints section
    """

    # @app.route('/api/settings/current-timers')
    # def api_current_timers():
    #     """
    #     Get current timers from Settings
    
    #     Returns JSON:
    #     {
    #         "main": {
    #             "timer_id": "...",
    #             "state": "...",
    #             ...
    #         },
    #         "penalties": [...]
    #     }
    #     """
    
    
    #     timers = Settings.get_current_timers()
    #     return jsonify(timers)


    # @app.route('/api/settings/current-timers/clear', methods=['POST'])
    # def api_clear_current_timers():
    #     """
    #     Clear all current timers (for testing/reset)
    #     """
    
    
    #     Settings.clear_timers()
    #     return jsonify({
    #         'success': True,
    #         'message': 'Timers cleared'
    #     })

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
    
    
        from app.models.game import Game
    
        settings = Settings.get_settings()
        current_timers = settings.get_current_timers()
    
        # Get period details if exists
        period_data = None
        if settings.current_period_id:
            period = Period.query.get(settings.current_period_id)
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
        if settings.current_game_id:
            game = Game.query.get(settings.current_game_id)
            if game:
                game_data = {
                    "id": game.id,
                    # Add other game fields as needed
                }

        is_reversed = False
        if settings.is_scoreboard_reversed:
            is_reversed = True
    
        return jsonify({
            "current_season_id": settings.current_season_id,
            "current_game_id": settings.current_game_id,
            "current_period_id": settings.current_period_id,
            "current_timers": current_timers,
            "period": period_data,
            "game": game_data,
            "is_reversed": is_reversed
        })

    # @app.route('/api/scoreboard-state', methods=['GET', 'POST'])
    # def get_scoreboard_state():
    
    #     settings = Settings.query.get(1)
    #     if not settings:
    #         settings = Settings(id=1, is_scoreboard_reversed=False)
    #         db.session.add(settings)
    #         db.session.commit()

    #     if request.method == 'POST':
    #         data = request.get_json()
    #         settings.is_scoreboard_reversed = data.get('is_reversed', False)
    #         settings.updated_at = datetime.utcnow()
    #         db.session.add(settings)
    #         db.session.commit()
    
    #         return jsonify({'success': True, 'is_reversed': settings.is_scoreboard_reversed})
    
    #     return jsonify({
    #         'is_reversed': settings.is_scoreboard_reversed
    #     })

    @app.route('/teams/<int:team_id>/scrape-players')
    def scrape_players(team_id):
        """Start scraping players for a team in background thread, return JSON"""
        from flask import jsonify
        if player_scraper_manager.is_scraping_in_progress():
            return jsonify({'error': 'Scrapowanie zawodników już trwa'}), 409
        started = player_scraper_manager.scrape_players_async(team_id)
        if started:
            return jsonify({'status': 'started'}), 202
        return jsonify({'error': 'Nie można rozpocząć scrapowania — sprawdź czy drużyna ma skonfigurowany URL'}), 400

    # =========================
    # ASSIGNMENT API
    # =========================

    @app.route('/api/assign/<content_type>/data')
    def api_assign_data(content_type):
        """Return JSON with assigned and available elements for the assignment modal."""
        from flask import jsonify
    
        from app.models.game import Game
        from core.managers.game_player_manager import GamePlayerManager
        from app.managers.player_manager import PlayerManager
        from core.managers.game_referee_manager import GameRefereeManager
        from app.managers.referee_manager import RefereeManager
        from core.managers.game_commentator_manager import GameCommentatorManager
        from app.managers.commentator_manager import CommentatorManager
        from core.managers.game_camera_manager import GameCameraManager
        from core.managers.camera_manager import CameraManager
        from core.models.game_camera import VALID_HDMI_INPUTS, HDMI_DEFAULT_LOCATION
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

        # ── referees ─────────────────────────────────────────────────────────────
        if content_type == 'referees':
            from core.models.game_referee import GameReferee
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
            from core.models.game_commentator import GameCommentator
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
                from core.managers.game_player_manager import GamePlayerManager
                from app.models.game_player import GamePlayer
                team_id = game.home_team_id if content_type == 'home-squad' else game.away_team_id

                pg_mgr = GamePlayerManager()
                # Remove all current assignments for this team in this game
                existing = GamePlayer.query.filter_by(game_id=game_id, team_id=team_id).all()
            
                for pg in existing:
                    db.session.delete(pg)
                db.session.commit()

                # Re-assign from submitted list
                for item in data.get('assigned', []):
                    pg_mgr.assign_player_to_game(item['player_id'], game_id)
                return jsonify({'ok': True})

            # ── referees ─────────────────────────────────────────────────────────
            if content_type == 'referees':
                from core.managers.game_referee_manager import GameRefereeManager
                from core.models.game_referee import GameReferee
            

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
                from core.managers.game_commentator_manager import GameCommentatorManager
                from core.models.game_commentator import GameCommentator
            

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
                from core.managers.game_camera_manager import GameCameraManager
                from core.models.game_camera import GameCamera
            

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


    @app.route('/api/player/<int:player_id>', methods=['PATCH'])
    def api_patch_player(player_id):
        """Update Player base record (first_name, last_name)."""
        from flask import jsonify, request as req
        from app.models.player import Player
    

        player = Player.query.get(player_id)
        if not player:
            return jsonify({'error': 'Nie znaleziono zawodnika'}), 404

        data = req.get_json()
        try:
            if 'first_name' in data:
                player.first_name = data['first_name'].strip()
            if 'last_name' in data:
                player.last_name = data['last_name'].strip()
            db.session.commit()
            return jsonify({'ok': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

    # =========================
    # Uniforms API
    # =========================

    @app.route('/api/assign/uniforms/data')
    def api_uniforms_data():
        """Return uniform options for both teams of the current game."""
        import json as _json
    
        from app.models.game import Game

        settings = Settings.get_settings()
        if not settings.current_game_id:
            return jsonify({'error': 'Brak wybranego meczu'}), 400

        game = Game.query.get(settings.current_game_id)
        if not game:
            return jsonify({'error': 'Nie znaleziono meczu'}), 404

        DEFAULT_EXTRA = '#9eff00'
        DEFAULT_GAME  = '#000'   # sentinel – means "not assigned"

        def _parse(raw, fallback):
            """Parse JSON string, return list; on error return fallback."""
            if not raw:
                return fallback
            try:
                v = _json.loads(raw)
                return v if isinstance(v, list) else fallback
            except Exception:
                return fallback

        def _team_options(team, game_uniform_raw):
            """
            Build option list for one team side.

            Returns dict:
              options: [{'colors': [...], 'source': 'home'|'away'|'extra'}]
              selected_colors: list currently saved in game (or None)
              extra_colors: colors to pre-fill in the editable extra option
            """
            team_uniform = team.get_uniform()   # {'home': [...], 'away': [...]}
            home_colors  = team_uniform.get('home') or []
            away_colors  = team_uniform.get('away') or []
            game_colors  = _parse(game_uniform_raw, None)

            options = []
            if home_colors:
                options.append({'colors': home_colors, 'source': 'home'})
            if away_colors:
                options.append({'colors': away_colors, 'source': 'away'})

            # Determine default for the editable extra option.
            # If the game already has colors saved and they don't match home/away,
            # use those saved colors as the extra default.
            is_default_game = (game_colors is None or game_colors == [DEFAULT_GAME])
            known_sets = [home_colors, away_colors]
            if is_default_game or game_colors in known_sets:
                extra_colors = [DEFAULT_EXTRA]
            else:
                extra_colors = game_colors  # previously saved custom value

            options.append({'colors': extra_colors, 'source': 'extra'})

            return {
                'options': options,
                'selected_colors': game_colors,
            }

        home_data = _team_options(game.home_team, game.home_team_uniform)
        away_data = _team_options(game.away_team, game.away_team_uniform)

        return jsonify({
            'home_team_id':   game.home_team_id,
            'home_team_name': game.home_team.name,
            'home':           home_data,
            'away_team_id':   game.away_team_id,
            'away_team_name': game.away_team.name,
            'away':           away_data,
        })


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


    """Routes for Season, League and Game CRUD operations"""
    from flask import render_template, jsonify, current_app, flash, redirect, url_for, request
    from app.managers.season_manager import SeasonManager
    from app.managers.league_manager import LeagueManager
    from core.managers.game_manager import GameManager
    from core.managers.camera_manager import CameraManager
    from core.managers.game_camera_manager import GameCameraManager
    from core.models.stadium import Stadium
    from app.models.team import Team
    from datetime import datetime
    import logging

    logger = logging.getLogger(__name__)

    season_manager = SeasonManager()
    league_manager = LeagueManager()
    game_manager = GameManager()


    # =========================
    # SEASON ROUTES
    # =========================

    # @app.route('/seasons/')
    # def list_seasons():
    #     """List all seasons"""
    #     seasons = season_manager.get_all_seasons()
    #     return render_template('seasons/list.html', seasons=seasons)


    # @app.route('/seasons/<int:season_id>')
    # def view_season(season_id):
    #     """View season details with statistics"""
    #     stats = season_manager.get_season_statistics(season_id)
    
    #     if not stats:
    #         flash('Nie znaleziono sezonu', 'error')
    #         return redirect(url_for('list_seasons'))
    
    #     return render_template('seasons/view.html', stats=stats)


    # @app.route('/seasons/create', methods=['GET', 'POST'])
    # def create_season():
    #     """Create new season"""
    #     if request.method == 'POST':
    #         try:
    #             season = season_manager.create_season(
    #                 number=int(request.form['number']),
    #                 name=request.form['name']
    #             )
            
    #             flash(f'Utworzono sezon: {season.name}', 'success')
    #             return redirect(url_for('view_season', season_id=season.id))
            
    #         except ValueError as e:
    #             flash(str(e), 'error')
    #         except Exception as e:
    #             logger.error(f"Error creating season: {e}")
    #             flash(f'Błąd podczas tworzenia sezonu: {str(e)}', 'error')
    
    #     return render_template('seasons/create.html')


    # @app.route('/seasons/<int:season_id>/edit', methods=['GET', 'POST'])
    # def edit_season(season_id):
    #     """Edit existing season"""
    #     season = season_manager.get_season_by_id(season_id)
    
    #     if not season:
    #         flash('Nie znaleziono sezonu', 'error')
    #         return redirect(url_for('list_seasons'))
    
    #     if request.method == 'POST':
    #         try:
    #             season_manager.update_season(
    #                 season_id=season_id,
    #                 number=int(request.form.get('number')) if request.form.get('number') else None,
    #                 name=request.form.get('name')
    #             )
            
    #             flash(f'Zaktualizowano sezon: {season.name}', 'success')
    #             return redirect(url_for('view_season', season_id=season.id))
            
    #         except ValueError as e:
    #             flash(str(e), 'error')
    #         except Exception as e:
    #             logger.error(f"Error updating season: {e}")
    #             flash(f'Błąd podczas aktualizacji sezonu: {str(e)}', 'error')
    
    #     return render_template('seasons/edit.html', season=season)


    # @app.route('/seasons/<int:season_id>/delete', methods=['POST'])
    # def delete_season(season_id):
    #     """Delete season"""
    #     season = season_manager.get_season_by_id(season_id)
    
    #     if not season:
    #         flash('Nie znaleziono sezonu', 'error')
    #         return redirect(url_for('list_seasons'))
    
    #     season_name = season.name
    
    #     try:
    #         if season_manager.delete_season(season_id):
    #             flash(f'Usunięto sezon: {season_name}', 'success')
    #         else:
    #             flash('Błąd podczas usuwania sezonu', 'error')
    #     except ValueError as e:
    #         flash(str(e), 'error')
    
    #     return redirect(url_for('list_seasons'))


    # =========================
    # LEAGUE ROUTES
    # =========================

    # @app.route('/leagues/')
    # @app.route('/seasons/<int:season_id>/leagues/')
    # def list_leagues(season_id=None):
    #     """List all leagues, optionally filtered by season"""
    #     leagues = league_manager.get_all_leagues(season_id=season_id)
    #     season = season_manager.get_season_by_id(season_id) if season_id else None
    
    #     return render_template('leagues/list.html', 
    #                           leagues=leagues, 
    #                           season=season)


    # @app.route('/leagues/<int:league_id>')
    # def view_league(league_id):
    #     """View league details with statistics"""
    #     stats = league_manager.get_league_statistics(league_id)
    
    #     if not stats:
    #         flash('Nie znaleziono ligi', 'error')
    #         return redirect(url_for('list_leagues'))
    
    #     return render_template('leagues/view.html', stats=stats)


    # @app.route('/leagues/create', methods=['GET', 'POST'])
    # @app.route('/seasons/<int:season_id>/leagues/create', methods=['GET', 'POST'])
    # def create_league(season_id=None):
    #     """Create new league"""
    #     seasons = season_manager.get_all_seasons()
    
    #     if request.method == 'POST':
    #         try:
    #             selected_season_id = int(request.form.get('season_id', season_id or 0))
            
    #             league = league_manager.create_league(
    #                 season_id=selected_season_id,
    #                 name=request.form['name'],
    #                 games_url=request.form['games_url'],
    #                 scorers_url=request.form['scorers_url'],
    #                 assists_url=request.form['assists_url'],
    #                 canadian_url=request.form['canadian_url'],
    #                 table_url=request.form.get('table_url', ''),
    #                 allows_draw=('allows_draw' in request.form),
    #             )
            
    #             flash(f'Utworzono ligę: {league.name}', 'success')
    #             return redirect(url_for('view_league', league_id=league.id))
            
    #         except ValueError as e:
    #             flash(str(e), 'error')
    #         except Exception as e:
    #             logger.error(f"Error creating league: {e}")
    #             flash(f'Błąd podczas tworzenia ligi: {str(e)}', 'error')
    
    #     return render_template('leagues/create.html', 
    #                           seasons=seasons, 
    #                           selected_season_id=season_id)


    # @app.route('/leagues/<int:league_id>/edit', methods=['GET', 'POST'])
    # def edit_league(league_id):
    #     """Edit existing league"""
    #     league = league_manager.get_league_by_id(league_id)
    
    #     if not league:
    #         flash('Nie znaleziono ligi', 'error')
    #         return redirect(url_for('list_leagues'))
    
    #     if request.method == 'POST':
    #         try:
    #             league_manager.update_league(
    #                 league_id=league_id,
    #                 name=request.form.get('name'),
    #                 games_url=request.form.get('games_url'),
    #                 table_url=request.form.get('table_url'),
    #                 scorers_url=request.form.get('scorers_url'),
    #                 assists_url=request.form.get('assists_url'),
    #                 canadian_url=request.form.get('canadian_url'),
    #                 allows_draw=('allows_draw' in request.form),
    #             )
            
    #             flash(f'Zaktualizowano ligę: {league.name}', 'success')
    #             return redirect(url_for('view_league', league_id=league.id))
            
    #         except ValueError as e:
    #             flash(str(e), 'error')
    #         except Exception as e:
    #             logger.error(f"Error updating league: {e}")
    #             flash(f'Błąd podczas aktualizacji ligi: {str(e)}', 'error')
    
    #     return render_template('leagues/edit.html', league=league)


    # @app.route('/leagues/<int:league_id>/delete', methods=['POST'])
    # def delete_league(league_id):
    #     """Delete league"""
    #     league = league_manager.get_league_by_id(league_id)
    
    #     if not league:
    #         flash('Nie znaleziono ligi', 'error')
    #         return redirect(url_for('list_leagues'))
    
    #     league_name = league.name
    #     season_id = league.season_id
    
    #     try:
    #         if league_manager.delete_league(league_id):
    #             flash(f'Usunięto ligę: {league_name}', 'success')
    #             return redirect(url_for('list_leagues', season_id=season_id))
    #         else:
    #             flash('Błąd podczas usuwania ligi', 'error')
    #     except ValueError as e:
    #         flash(str(e), 'error')
    
    #     return redirect(url_for('list_leagues'))


    # # =========================
    # # LEAGUE TEAMS MANAGEMENT
    # # =========================

    # @app.route('/leagues/<int:league_id>/teams')
    # def league_teams(league_id):
    #     """Manage teams in a league"""
    #     league = league_manager.get_league_by_id(league_id)
    
    #     if not league:
    #         flash('Nie znaleziono ligi', 'error')
    #         return redirect(url_for('list_leagues'))
    
    #     teams = league_manager.get_league_teams(league_id)
    #     available_teams = league_manager.get_available_teams(league_id)
    
    #     return render_template('leagues/teams.html',
    #                           league=league,
    #                           teams=teams,
    #                           available_teams=available_teams)


    # @app.route('/leagues/<int:league_id>/teams/add', methods=['POST'])
    # def add_team_to_league(league_id):
    #     """Add team to league"""
    #     try:
    #         team_id = int(request.form['team_id'])
    #         group_nr = int(request.form.get('group_nr', 1))
        
    #         league_manager.add_team_to_league(league_id, team_id, group_nr)
    #         flash('Dodano zespół do ligi', 'success')
        
    #     except ValueError as e:
    #         flash(str(e), 'error')
    #     except Exception as e:
    #         logger.error(f"Error adding team to league: {e}")
    #         flash(f'Błąd: {str(e)}', 'error')
    
    #     return redirect(url_for('league_teams', league_id=league_id))


    # @app.route('/leagues/<int:league_id>/teams/<int:team_id>/remove', methods=['POST'])
    # def remove_team_from_league(league_id, team_id):
    #     """Remove team from league"""
    #     try:
    #         if league_manager.remove_team_from_league(league_id, team_id):
    #             flash('Usunięto zespół z ligi', 'success')
    #         else:
    #             flash('Błąd podczas usuwania zespołu', 'error')
            
    #     except ValueError as e:
    #         flash(str(e), 'error')
    #     except Exception as e:
    #         logger.error(f"Error removing team from league: {e}")
    #         flash(f'Błąd: {str(e)}', 'error')
    
    #     return redirect(url_for('league_teams', league_id=league_id))


    # @app.route('/leagues/<int:league_id>/teams/<int:team_id>/group', methods=['POST'])
    # def update_team_group(league_id, team_id):
    #     """Update team's group in league"""
    #     try:
    #         group_nr = int(request.form['group_nr'])
        
    #         if league_manager.update_team_group(league_id, team_id, group_nr):
    #             flash('Zaktualizowano grupę zespołu', 'success')
    #         else:
    #             flash('Błąd podczas aktualizacji grupy', 'error')
            
    #     except ValueError as e:
    #         flash(str(e), 'error')
    #     except Exception as e:
    #         logger.error(f"Error updating team group: {e}")
    #         flash(f'Błąd: {str(e)}', 'error')
    
    #     return redirect(url_for('league_teams', league_id=league_id))


    # # =========================
    # # MATCH ROUTES
    # # =========================

    # # @app.route('/games/')
    # @app.route('/leagues/<int:league_id>/games/')
    # def league_games(league_id=None):
    #     """List all games, optionally filtered by league"""
    #     games = game_manager.get_all_games(league_id=league_id)
    #     league = league_manager.get_league_by_id(league_id) if league_id else None

    #     return render_template('games/list.html',
    #                           games=games,
    #                           league=league)


    # @app.route('/games/<int:game_id>')
    # def view_game(game_id):
    #     """View game details"""
    #     game = game_manager.get_game_by_id(game_id)
    
    #     if not game:
    #         flash('Nie znaleziono meczu', 'error')
    #         return redirect(url_for('list_games'))
    
    #     return render_template('games/view.html', game=game)


    # @app.route('/games/create', methods=['GET', 'POST'])
    # @app.route('/leagues/<int:league_id>/games/create', methods=['GET', 'POST'])
    # def create_game(league_id=None):
    #     """Create new game"""
    #     leagues = league_manager.get_all_leagues()
    #     teams = Team.query.order_by(Team.name).all()
    #     stadiums = Stadium.query.order_by(Stadium.city, Stadium.name).all()
    
    #     if request.method == 'POST':
    #         try:
    #             selected_league_id = int(request.form.get('league_id', league_id or 0))
            
    #             # Parse date if provided
    #             game_date = None
    #             if request.form.get('date') and request.form.get('time'):
    #                 date_str = f"{request.form['date']} {request.form['time']}"
    #                 game_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            
    #             game = game_manager.create_game(
    #                 home_team_id=int(request.form['home_team_id']),
    #                 away_team_id=int(request.form['away_team_id']),
    #                 league_id=selected_league_id,
    #                 stadium_id=int(request.form['stadium_id']),
    #                 round_number=int(request.form['round']),
    #                 group_nr=int(request.form.get('group_nr', 1)),
    #                 date=game_date
    #             )
            
    #             flash(f'Utworzono mecz', 'success')
    #             return redirect(url_for('view_game', game_id=game.id))
            
    #         except ValueError as e:
    #             flash(str(e), 'error')
    #         except Exception as e:
    #             logger.error(f"Error creating game: {e}")
    #             flash(f'Błąd podczas tworzenia meczu: {str(e)}', 'error')
    
    #     return render_template('games/create.html',
    #                           leagues=leagues,
    #                           teams=teams,
    #                           stadiums=stadiums,
    #                           selected_league_id=league_id)


    # @app.route('/games/<int:game_id>/edit', methods=['GET', 'POST'])
    # def edit_game(game_id):
    #     """Edit existing game"""
    #     from app.managers.shootout_manager import ShootoutManager
    
    #     game = game_manager.get_game_by_id(game_id)
    
    #     if not game:
    #         flash('Nie znaleziono meczu', 'error')
    #         return redirect(url_for('list_games'))
    
    #     teams = Team.query.order_by(Team.name).all()
    #     stadiums = Stadium.query.order_by(Stadium.city, Stadium.name).all()
    #     shootout_manager = ShootoutManager()
    
    #     if request.method == 'POST':
    #         try:
    #             # Parse date if provided
    #             game_date = None
    #             if request.form.get('date') and request.form.get('time'):
    #                 date_str = f"{request.form['date']} {request.form['time']}"
    #                 game_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            
    #             game_manager.update_game(
    #                 game_id=game_id,
    #                 home_team_id=int(request.form.get('home_team_id')) if request.form.get('home_team_id') else None,
    #                 away_team_id=int(request.form.get('away_team_id')) if request.form.get('away_team_id') else None,
    #                 home_team_goals=int(request.form.get('home_team_goals')) if request.form.get('home_team_goals') else None,
    #                 away_team_goals=int(request.form.get('away_team_goals')) if request.form.get('away_team_goals') else None,
    #                 is_home_team_lost_by_wo=int(request.form.get('is_home_team_lost_by_wo')) if request.form.get('is_home_team_lost_by_wo') else None,
    #                 is_away_team_lost_by_wo=int(request.form.get('is_away_team_lost_by_wo')) if request.form.get('is_away_team_lost_by_wo') else None,
    #                 stadium_id=int(request.form.get('stadium_id')) if request.form.get('stadium_id') else None,
    #                 date=game_date,
    #                 round_number=int(request.form.get('round')) if request.form.get('round') else None,
    #                 group_nr=int(request.form.get('group_nr')) if request.form.get('group_nr') else None
    #             )
            
    #             # Update penalty shootout if exists
    #             if game.shootout:
    #                 home_penalties = request.form.get('home_team_penalties')
    #                 away_penalties = request.form.get('away_team_penalties')
                
    #                 if home_penalties is not None and away_penalties is not None:
    #                     shootout_manager.update_shootout_score(
    #                         shootout_id=game.shootout.id,
    #                         home_penalties=int(home_penalties),
    #                         away_penalties=int(away_penalties)
    #                     )
            
    #             flash(f'Zaktualizowano mecz', 'success')
    #             return redirect(url_for('view_game', game_id=game.id))
            
    #         except ValueError as e:
    #             flash(str(e), 'error')
    #         except Exception as e:
    #             logger.error(f"Error updating game: {e}")
    #             flash(f'Błąd podczas aktualizacji meczu: {str(e)}', 'error')
    
    #     return render_template('games/edit.html',
    #                           game=game,
    #                           teams=teams,
    #                           stadiums=stadiums)


    # @app.route('/games/<int:game_id>/prepare-broadcast')
    # def prepare_game_for_broadcast(game_id):
    #     """Prepare game for broadcast by creating default periods"""
    #     from core.managers.period_manager import PeriodManager
    
    #     game = game_manager.get_game_by_id(game_id)
    
    #     if not game:
    #         flash('Nie znaleziono meczu', 'error')
    #         return redirect(url_for('list_games'))
    
    #     # Check if game already has periods
    #     if game.periods.count() > 0:
    #         flash('Mecz ma już utworzone okresy', 'warning')
    #         return redirect(url_for('game_period_choice'))
    
    #     camera_manager = CameraManager()
    #     main_camera = camera_manager.get_camera_by_id(1)
    #     if main_camera:
    #         game_camera_manager = GameCameraManager()
    #         game_camera_manager.assign_camera_to_game(game_id=game.id, camera_id=main_camera.id, hdmi_input=1, location='Główna')

    #     period_manager = PeriodManager()
    
    #     try:
    #         periods = period_manager.create_default_periods(game_id=game_id)
    #         flash(f'Utworzono {len(periods)} okresy dla meczu. Mecz gotowy do transmisji.', 'success')
    #     except ValueError as e:
    #         flash(str(e), 'error')
    #     except Exception as e:
    #         logger.error(f"Error preparing game for broadcast: {e}")
    #         flash(f'Błąd podczas przygotowania meczu: {str(e)}', 'error')
    
    #     return redirect(url_for('edit_game', game_id=game_id))


    # @app.route('/games/<int:game_id>/select-broadcast')
    # def select_game_for_broadcast(game_id):
    #     """Select game as current broadcast game"""
        

    #     game = game_manager.get_game_by_id(game_id)

    #     if not game:
    #         flash('Nie znaleziono meczu', 'error')
    #         return redirect(url_for('list_games'))

    #     # Check if game has periods
    #     if game.periods.count() == 0:
    #         flash('Mecz nie ma utworzonych okresów. Najpierw przygotuj mecz do transmisji.', 'error')
    #         return redirect(url_for('edit_game', game_id=game_id))

    #     try:
    #         # Resetuj stan poprzedniego meczu przed ustawieniem nowego.
    #         # Kolejność ma znaczenie: najpierw czyścimy pola zależne (period, timers, shootout),
    #         # potem ustawiamy nowy game_id — unikamy chwilowej niespójności w settings.
    #         Settings.set_current_period(None)
    #         Settings.clear_timers()
    #         Settings.set_current_shootout(None)
    #         Settings.set_current_game(game_id)

    #         flash(f'Wybrano mecz do transmisji: {game.home_team.short_name} vs {game.away_team.short_name}', 'success')

    #         # Notify UI clients (index.html, game-period-choice.html) via Flask-SocketIO
    #         from core.extensions import socketio
    #          socketio.emit('game_changed', {'game_id': game_id})

    #         # Notify stream overlay via hub
    #         from core.managers import get_hub_client
    #         hub_client = get_hub_client()
    #         if hub_client:
    #             hub_client.broadcast_to_class('overlay', 'reload', {'reason': 'game_changed'})

    #         return redirect(url_for('game_setup'))
    #     except Exception as e:
    #         logger.error(f"Error selecting game for broadcast: {e}")
    #         flash(f'Błąd podczas wyboru meczu: {str(e)}', 'error')
    #         return redirect(url_for('edit_game', game_id=game_id))


    # @app.route('/games/<int:game_id>/add-shootout')
    # def add_shootout(game_id):
    #     """Add penalty shootout to game"""
    #     from app.managers.shootout_manager import ShootoutManager
    
    #     game = game_manager.get_game_by_id(game_id)
    
    #     if not game:
    #         flash('Nie znaleziono meczu', 'error')
    #         return redirect(url_for('list_games'))
    
    #     # Check if penalty shootout already exists
    #     if game.shootout:
    #         flash('Rzuty karne są już dodane do tego meczu', 'warning')
    #         return redirect(url_for('edit_game', game_id=game_id))
    
    #     shootout_manager = ShootoutManager()
    
    #     try:
    #         shootout_manager.create_shootout(game_id=game_id)
    #         flash('Dodano rzuty karne do meczu', 'success')
    #     except ValueError as e:
    #         flash(str(e), 'error')
    #     except Exception as e:
    #         logger.error(f"Error adding penalty shootout: {e}")
    #         flash(f'Błąd podczas dodawania rzutów karnych: {str(e)}', 'error')
    
    #     return redirect(url_for('edit_game', game_id=game_id))


    # @app.route('/games/<int:game_id>/delete', methods=['POST'])
    # def delete_game(game_id):
    #     """Delete game"""
    #     game = game_manager.get_game_by_id(game_id)
    
    #     if not game:
    #         flash('Nie znaleziono meczu', 'error')
    #         return redirect(url_for('list_games'))
    
    #     league_id = game.league_id
    
    #     try:
    #         if game_manager.delete_game(game_id):
    #             flash('Usunięto mecz', 'success')
    #             return redirect(url_for('list_games', league_id=league_id))
    #         else:
    #             flash('Błąd podczas usuwania meczu', 'error')
    #     except ValueError as e:
    #         flash(str(e), 'error')
    
    #     return redirect(url_for('list_games'))


    # =========================
    # API ENDPOINTS
    # =========================

    # @app.route('/api/seasons')
    # def api_list_seasons():
    #     """API: List all seasons"""
    #     seasons = season_manager.get_all_seasons()
    #     return jsonify({
    #         'seasons': [season.to_dict() for season in seasons]
    #     })


    # @app.route('/api/seasons/<int:season_id>')
    # def api_get_season(season_id):
    #     """API: Get season with statistics"""
    #     stats = season_manager.get_season_statistics(season_id)
    
    #     if not stats:
    #         return jsonify({'error': 'Season not found'}), 404
    
    #     return jsonify(stats)


    # @app.route('/api/leagues')
    # def api_list_leagues():
    #     """API: List all leagues"""
    #     season_id = request.args.get('season_id', type=int)
    #     leagues = league_manager.get_all_leagues(season_id=season_id)
    
    #     return jsonify({
    #         'leagues': [league.to_dict() for league in leagues]
    #     })


    # @app.route('/api/leagues/<int:league_id>')
    # def api_get_league(league_id):
    #     """API: Get league with statistics"""
    #     stats = league_manager.get_league_statistics(league_id)
    
    #     if not stats:
    #         return jsonify({'error': 'League not found'}), 404
    
    #     return jsonify(stats)


    # @app.route('/api/games')
    # def api_list_games():
    #     """API: List all games"""
    #     league_id = request.args.get('league_id', type=int)
    #     team_id = request.args.get('team_id', type=int)
    #     status = request.args.get('status', type=int)
    
    #     games = game_manager.get_all_games(
    #         league_id=league_id,
    #         team_id=team_id,
    #         status=status
    #     )
    
    #     return jsonify({
    #         'games': [game.to_dict() for game in games]
    #     })


    # @app.route('/api/games/<int:game_id>')
    # def api_get_game(game_id):
    #     """API: Get single game"""
    #     game = game_manager.get_game_by_id(game_id)
    
    #     if not game:
    #         return jsonify({'error': 'Game not found'}), 404
    
    #     return jsonify(game.to_dict())

    # =========================
    # PLAYER ROUTES
    # =========================

    from app.managers.player_manager import PlayerManager
    from app.managers.team_manager import TeamManager as _TeamManager
    from app.models.player import Player

    _player_manager = PlayerManager()
    _team_manager_crud = _TeamManager()

    # @app.route('/teams/<int:team_id>/players')
    # def list_players(team_id):
    #     team = _team_manager_crud.get_team_by_id(team_id)
    #     if not team:
    #         flash('Nie znaleziono drużyny', 'error')
    #         return redirect(url_for('list_games'))
    #     players = _player_manager.get_players_by_team(team_id)
    #     return render_template('players/list.html', team=team, players=players)

    # @app.route('/teams/<int:team_id>/players/create', methods=['GET', 'POST'])
    # def create_player(team_id):
    #     team = _team_manager_crud.get_team_by_id(team_id)
    #     if not team:
    #         flash('Nie znaleziono drużyny', 'error')
    #         return redirect(url_for('list_games'))
    #     if request.method == 'POST':
    #         try:
    #             _player_manager.create_player(
    #                 first_name=request.form['first_name'].strip(),
    #                 last_name=request.form['last_name'].strip(),
    #                 team_id=team_id,
    #                 number=int(request.form['number']) if request.form.get('number') else None,
    #                 is_goalkeeper='is_goalkeeper' in request.form,
    #                 is_captain='is_captain' in request.form,
    #             )
    #             flash('Zawodnik został dodany', 'success')
    #             return redirect(url_for('list_players', team_id=team_id))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('players/form.html', team=team, player=None)

    # @app.route('/players/<int:player_id>/edit', methods=['GET', 'POST'])
    # def edit_player(player_id):
    #     player = _player_manager.get_player_by_id(player_id)
    #     if not player:
    #         flash('Nie znaleziono zawodnika', 'error')
    #         return redirect(url_for('list_games'))
    #     if request.method == 'POST':
    #         try:
    #             _player_manager.update_player(
    #                 player_id=player_id,
    #                 first_name=request.form['first_name'].strip(),
    #                 last_name=request.form['last_name'].strip(),
    #                 number=int(request.form['number']) if request.form.get('number') else None,
    #                 is_goalkeeper='is_goalkeeper' in request.form,
    #                 is_captain='is_captain' in request.form,
    #             )
    #             flash('Zawodnik zaktualizowany', 'success')
    #             return redirect(url_for('list_players', team_id=player.team_id))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('players/form.html', team=player.team, player=player)

    # @app.route('/players/<int:player_id>/delete', methods=['POST'])
    # def delete_player(player_id):
    #     player = _player_manager.get_player_by_id(player_id)
    #     if not player:
    #         flash('Nie znaleziono zawodnika', 'error')
    #         return redirect(url_for('list_games'))
    #     team_id = player.team_id
    #     _player_manager.delete_player(player_id)
    #     flash('Zawodnik usunięty', 'success')
    #     return redirect(url_for('list_players', team_id=team_id))


    # # =========================
    # # STADIUM ROUTES
    # # =========================

    # from app.managers.stadium_manager import StadiumManager as _StadiumManager

    # _stadium_manager = _StadiumManager()

    # @app.route('/stadiums')
    # def list_stadiums():
    #     stadiums = _stadium_manager.get_all_stadiums()
    #     return render_template('stadiums/list.html', stadiums=stadiums)

    # @app.route('/stadiums/create', methods=['GET', 'POST'])
    # def create_stadium():
    #     if request.method == 'POST':
    #         try:
    #             _stadium_manager.create_stadium(
    #                 name=request.form['name'].strip(),
    #                 address=request.form['address'].strip(),
    #                 city=request.form['city'].strip(),
    #             )
    #             flash('Stadion dodany', 'success')
    #             return redirect(url_for('list_stadiums'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('stadiums/form.html', stadium=None)

    # @app.route('/stadiums/<int:stadium_id>/edit', methods=['GET', 'POST'])
    # def edit_stadium(stadium_id):
    #     stadium = _stadium_manager.get_stadium_by_id(stadium_id)
    #     if not stadium:
    #         flash('Nie znaleziono stadionu', 'error')
    #         return redirect(url_for('list_stadiums'))
    #     if request.method == 'POST':
    #         try:
    #             _stadium_manager.update_stadium(
    #                 stadium_id=stadium_id,
    #                 name=request.form['name'].strip(),
    #                 address=request.form['address'].strip(),
    #                 city=request.form['city'].strip(),
    #             )
    #             flash('Stadion zaktualizowany', 'success')
    #             return redirect(url_for('list_stadiums'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('stadiums/form.html', stadium=stadium)

    # @app.route('/stadiums/<int:stadium_id>/delete', methods=['POST'])
    # def delete_stadium(stadium_id):
    #     _stadium_manager.delete_stadium(stadium_id)
    #     flash('Stadion usunięty', 'success')
    #     return redirect(url_for('list_stadiums'))


    # # =========================
    # # REFEREE ROUTES
    # # =========================

    # from app.managers.referee_manager import RefereeManager as _RefereeManager

    # _referee_manager = _RefereeManager()

    # @app.route('/referees')
    # def list_referees():
    #     referees = _referee_manager.get_all_referees()
    #     return render_template('referees/list.html', referees=referees)

    # @app.route('/referees/create', methods=['GET', 'POST'])
    # def create_referee():
    #     if request.method == 'POST':
    #         try:
    #             _referee_manager.create_referee(
    #                 first_name=request.form['first_name'].strip(),
    #                 last_name=request.form['last_name'].strip(),
    #             )
    #             flash('Sędzia dodany', 'success')
    #             return redirect(url_for('list_referees'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('referees/form.html', referee=None)

    # @app.route('/referees/<int:referee_id>/edit', methods=['GET', 'POST'])
    # def edit_referee(referee_id):
    #     referee = _referee_manager.get_referee_by_id(referee_id)
    #     if not referee:
    #         flash('Nie znaleziono sędziego', 'error')
    #         return redirect(url_for('list_referees'))
    #     if request.method == 'POST':
    #         try:
    #             _referee_manager.update_referee(
    #                 referee_id=referee_id,
    #                 first_name=request.form['first_name'].strip(),
    #                 last_name=request.form['last_name'].strip(),
    #             )
    #             flash('Sędzia zaktualizowany', 'success')
    #             return redirect(url_for('list_referees'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('referees/form.html', referee=referee)

    # @app.route('/referees/<int:referee_id>/delete', methods=['POST'])
    # def delete_referee(referee_id):
    #     _referee_manager.delete_referee(referee_id)
    #     flash('Sędzia usunięty', 'success')
    #     return redirect(url_for('list_referees'))


    # # =========================
    # # COMMENTATOR ROUTES
    # # =========================

    # from app.managers.commentator_manager import CommentatorManager as _CommentatorManager

    # _commentator_manager = _CommentatorManager()

    # @app.route('/commentators')
    # def list_commentators():
    #     commentators = _commentator_manager.get_all_commentators()
    #     return render_template('commentators/list.html', commentators=commentators)

    # @app.route('/commentators/create', methods=['GET', 'POST'])
    # def create_commentator():
    #     if request.method == 'POST':
    #         try:
    #             _commentator_manager.create_commentator(
    #                 first_name=request.form['first_name'].strip(),
    #                 last_name=request.form['last_name'].strip(),
    #             )
    #             flash('Komentator dodany', 'success')
    #             return redirect(url_for('list_commentators'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('commentators/form.html', commentator=None)

    # @app.route('/commentators/<int:commentator_id>/edit', methods=['GET', 'POST'])
    # def edit_commentator(commentator_id):
    #     commentator = _commentator_manager.get_commentator_by_id(commentator_id)
    #     if not commentator:
    #         flash('Nie znaleziono komentatora', 'error')
    #         return redirect(url_for('list_commentators'))
    #     if request.method == 'POST':
    #         try:
    #             _commentator_manager.update_commentator(
    #                 commentator_id=commentator_id,
    #                 first_name=request.form['first_name'].strip(),
    #                 last_name=request.form['last_name'].strip(),
    #             )
    #             flash('Komentator zaktualizowany', 'success')
    #             return redirect(url_for('list_commentators'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('commentators/form.html', commentator=commentator)

    # @app.route('/commentators/<int:commentator_id>/delete', methods=['POST'])
    # def delete_commentator(commentator_id):
    #     _commentator_manager.delete_commentator(commentator_id)
    #     flash('Komentator usunięty', 'success')
    #     return redirect(url_for('list_commentators'))


    # # =========================
    # # CAMERA ROUTES
    # # =========================

    # _camera_manager_crud = CameraManager()

    # @app.route('/cameras')
    # def list_cameras():
    #     cameras = _camera_manager_crud.get_all_cameras()
    #     return render_template('cameras/list.html', cameras=cameras)

    # @app.route('/cameras/create', methods=['GET', 'POST'])
    # def create_camera():
    #     if request.method == 'POST':
    #         try:
    #             _camera_manager_crud.create_camera(
    #                 name=request.form['name'].strip(),
    #                 brand=request.form['brand'].strip(),
    #                 model=request.form['model'].strip(),
    #             )
    #             flash('Kamera dodana', 'success')
    #             return redirect(url_for('list_cameras'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('cameras/form.html', camera=None)

    # @app.route('/cameras/<int:camera_id>/edit', methods=['GET', 'POST'])
    # def edit_camera(camera_id):
    #     camera = _camera_manager_crud.get_camera_by_id(camera_id)
    #     if not camera:
    #         flash('Nie znaleziono kamery', 'error')
    #         return redirect(url_for('list_cameras'))
    #     if request.method == 'POST':
    #         try:
    #             _camera_manager_crud.update_camera(
    #                 camera_id=camera_id,
    #                 name=request.form['name'].strip(),
    #                 brand=request.form['brand'].strip(),
    #                 model=request.form['model'].strip(),
    #             )
    #             flash('Kamera zaktualizowana', 'success')
    #             return redirect(url_for('list_cameras'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('cameras/form.html', camera=camera)

    # @app.route('/cameras/<int:camera_id>/delete', methods=['POST'])
    # def delete_camera(camera_id):
    #     _camera_manager_crud.delete_camera(camera_id)
    #     flash('Kamera usunięta', 'success')
    #     return redirect(url_for('list_cameras'))


    # =========================
    # EVENT ROUTES
    # =========================

    from app.managers.event_manager import EventManager as _EventManager

    _event_manager = _EventManager()

    # @app.route('/events')
    # def list_events():
    #     events = _event_manager.get_all_events()
    #     return render_template('events/list.html', events=events)

    # @app.route('/events/create', methods=['GET', 'POST'])
    # def create_event():
    #     if request.method == 'POST':
    #         try:
    #             _event_manager.create_event(
    #                 name=request.form['name'].strip(),
    #                 short_name=request.form['short_name'].strip(),
    #                 is_reported='is_reported' in request.form,
    #                 player_from_opponent='player_from_opponent' in request.form,
    #                 image_path=request.form.get('image_path', '').strip() or None,
    #             )
    #             flash('Zdarzenie dodane', 'success')
    #             return redirect(url_for('list_events'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('events/form.html', event=None)

    # @app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
    # def edit_event(event_id):
    #     event = _event_manager.get_event_by_id(event_id)
    #     if not event:
    #         flash('Nie znaleziono zdarzenia', 'error')
    #         return redirect(url_for('list_events'))
    #     if request.method == 'POST':
    #         try:
    #             _event_manager.update_event(
    #                 event_id=event_id,
    #                 name=request.form['name'].strip(),
    #                 short_name=request.form['short_name'].strip(),
    #                 is_reported='is_reported' in request.form,
    #                 player_from_opponent='player_from_opponent' in request.form,
    #                 image_path=request.form.get('image_path', '').strip() or None,
    #             )
    #             flash('Zdarzenie zaktualizowane', 'success')
    #             return redirect(url_for('list_events'))
    #         except Exception as e:
    #             flash(f'Błąd: {e}', 'error')
    #     return render_template('events/form.html', event=event)

    # @app.route('/events/<int:event_id>/delete', methods=['POST'])
    # def delete_event(event_id):
    #     _event_manager.delete_event(event_id)
    #     flash('Zdarzenie usunięte', 'success')
    #     return redirect(url_for('list_events'))

    # =============================================================================
    # GAME STATUS API
    # =============================================================================

    # @app.route('/api/games/<int:game_id>/status', methods=['PATCH'])
    # def api_update_game_status(game_id):
    #     """API: Update game status. Body: {status: 0|1|2}"""
    #     from flask import jsonify
        
    #     game = game_manager.get_game_by_id(game_id)
    #     if not game:
    #         return jsonify({'error': 'Nie znaleziono meczu'}), 404
    #     data = request.get_json(silent=True) or {}
    #     new_status = data.get('status')
    #     if new_status not in (0, 1, 2):
    #         return jsonify({'error': 'Nieprawidłowy status (dozwolone: 0, 1, 2)'}), 400
    #     try:
    #         game.status = new_status
    #         db.session.commit()
    #         return jsonify({'ok': True, 'game': game.to_dict()})
    #     except Exception as e:
    #         db.session.rollback()
    #         return jsonify({'error': str(e)}), 500


    # @app.route('/api/games/scrape/status')
    # def api_games_scrape_status():
    #     """API: Get current game scraping status"""
    #     from app.managers.game_scraper_manager import GameScraperManager
    #     from flask import jsonify
    #     game_scraper_manager = GameScraperManager()
    #     status = game_scraper_manager.get_scraping_status()
    #     return jsonify(status)