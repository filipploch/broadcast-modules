"""All routes - MINIMAL"""
from flask import render_template, jsonify, current_app, flash, redirect, url_for, request
from app.extensions import db
# from app.models import Plugin

from app.managers.team_manager import TeamManager
from app.managers.team_scraper_manager import TeamScraperManager
from app.managers.game_manager import GameManager
from app.managers.game_scraper_manager import GameScraperManager
from app.managers.league_manager import LeagueManager
from app.models.team import Team
from app.models.period import Period
from app.models.settings import Settings
import logging
from datetime import datetime
import os

# Import CRUD routes for Season, League, Game
from app import routes_crud  # noqa: F401


logger = logging.getLogger(__name__)

team_manager = TeamManager()
team_scraper_manager = TeamScraperManager()
game_manager = GameManager()
game_scraper_manager = GameScraperManager()
league_manager = LeagueManager()

@current_app.route('/ui')
def ui_dashboard():
    """
    Main UI dashboard with Jinja2 rendering
    
    Renders timers server-side from Settings.current_timers
    JavaScript only handles WebSocket updates, not timer creation
    """
    from app.models.settings import Settings
    from app.models.period import Period
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
    penalties = current_timers.get('penalties')
    
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


@current_app.route('/')
def index():
    """Broadcast control panel - manage periods and game state"""
    from app.models.settings import Settings
    from app.models.game import Game
    from app.models.period import Period
    
    settings = Settings.get_settings()
    
    # Get actual game
    game = None
    periods = []
    penalty = None
    
    if settings.current_game_id:
        game = Game.query.get(settings.current_game_id)
        if game:
            periods = Period.query.filter_by(game_id=game.id).all()
            penalty = game.penalty
    
    return render_template('index.html',
                          game=game,
                          periods=periods,
                          penalty=penalty,
                          settings=settings)  # ADDED: Pass settings to template


@current_app.route('/period/<int:period_id>/start')
def start_period(period_id):
    """Start a period and redirect to UI dashboard"""
    from app.managers.period_manager import PeriodManager
    from app.models.settings import Settings
    from app.models.game import Game
    from app.managers import get_timer_manager

    timer_manager = get_timer_manager()
    _previous_main_timer_id = Settings.get_current_timers()['main']['timer_id']
    timer_manager.remove_timer(_previous_main_timer_id)

    period_manager = PeriodManager()
    period = period_manager.get_period_by_id(period_id)
    
    if not period:
        flash('Nie znaleziono okresu', 'error')
        return redirect(url_for('index'))
    
    # Check if this period can be started
    game = Game.query.get(period.game_id)
    if not game:
        flash('Nie znaleziono meczu', 'error')
        return redirect(url_for('index'))
    
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
                return redirect(url_for('index'))
    
    try:
        # Start the period
        period_manager.start_period(period_id)
        
        # Set period as actual in settings
        Settings.set_current_period(period_id)
        
        # If this is first period, set game as PENDING
        if period.period_order == 1:
            game.set_live()
            db.session.commit()
        
        flash(f'Rozpoczęto {period.description}', 'success')
        return redirect(url_for('ui_dashboard'))
        
    except Exception as e:
        logger.error(f"Error starting period: {e}")
        flash(f'Błąd podczas rozpoczynania okresu: {str(e)}', 'error')
        return redirect(url_for('index'))


@current_app.route('/period/<int:period_id>/finish')
def finish_period(period_id):
    """Finish a period and return to broadcast control"""
    from app.managers.period_manager import PeriodManager
    from app.models.settings import Settings
    from app.models.game import Game
    
    period_manager = PeriodManager()
    period = period_manager.get_period_by_id(period_id)
    
    if not period:
        flash('Nie znaleziono okresu', 'error')
        return redirect(url_for('index'))
    
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
        
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error finishing period: {e}")
        flash(f'Błąd podczas kończenia okresu: {str(e)}', 'error')
        return redirect(url_for('index'))


@current_app.route('/period/<int:period_id>/reset-status')
def reset_period_status(period_id):
    """Reset period status to NOT_STARTED (for error correction)"""
    from app.managers.period_manager import PeriodManager
    
    period_manager = PeriodManager()
    period = period_manager.get_period_by_id(period_id)
    
    if not period:
        flash('Nie znaleziono okresu', 'error')
        return redirect(url_for('index'))
    
    try:
        period_manager.set_period_status(period_id, Period.STATUS_NOT_STARTED)
        flash(f'Zresetowano status okresu: {period.description}', 'success')
    except Exception as e:
        logger.error(f"Error resetting period status: {e}")
        flash(f'Błąd podczas resetowania statusu: {str(e)}', 'error')
    
    return redirect(url_for('index'))


@current_app.route('/overlay/scoreboard')
def overlay_scoreboard():
    """Scoreboard overlay"""
    return render_template('overlays/scoreboard.html')


@current_app.route('/api/status')
def api_status():
    """Application status"""
    return jsonify({
        'status': 'running',
        'module_id': current_app.config['MODULE_ID']
    })

@current_app.route('/games/')
def list_games():
    """List all games in database"""
    games = game_manager.get_all_games()
    stats = game_scraper_manager.get_statistics()
    scraping_status = game_scraper_manager.get_scraping_status()

    return render_template('games/list.html',
                           games=games,
                           stats=stats,
                           scraping_status=scraping_status)

@current_app.route('/teams/')
def list_teams():
    """List all teams in database"""
    teams = team_manager.get_all_teams()
    stats = team_scraper_manager.get_statistics()
    scraping_status = team_scraper_manager.get_scraping_status()

    return render_template('teams/list.html',
                           teams=teams,
                           stats=stats,
                           scraping_status=scraping_status)


@current_app.route('/teams/<int:team_id>')
def view_team(team_id):
    """View single team details"""
    team = team_manager.get_team_by_id(team_id)

    if not team:
        flash('Nie znaleziono zespołu', 'error')
        return redirect(url_for('list_teams'))

    logos_dir = 'static/images/logos'
    logos = []

    if os.path.exists(logos_dir):
        allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
        for file in os.listdir(logos_dir):
            if any(file.lower().endswith(ext) for ext in allowed_extensions):
                logos.append({
                    'filename': file,
                    'path': f'/static/images/logos/{file}'
                })

    return render_template('teams/view.html', team=team)


@current_app.route('/teams/create', methods=['GET', 'POST'])
def create_team():
    """Create new team manually (without scraping)"""
    if request.method == 'POST':
        try:
            uniform_home = request.form.getlist('uniform_home[]')
            uniform_away = request.form.getlist('uniform_away[]')
            team = team_manager.create_team(
                name=request.form['name'],
                name_20=request.form['name_20'],
                short_name=request.form['short_name'],
                team_url=request.form['team_url'],
                logo_path=request.form.get('logo_path', 'static/images/logos/default.png'),
                uniform={'home': uniform_home, 'away': uniform_away}
            )

            flash(f'Dodano zespół: {name}', 'success')
            return redirect(url_for('view_team', team_id=team.id))

        except Exception as e:
            logger.error(f"Error creating team: {e}")
            flash(f'Błąd podczas tworzenia zespołu: {str(e)}', 'error')

    return render_template('teams/create.html')


@current_app.route('/teams/<int:team_id>/edit', methods=['GET', 'POST'])
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
                name_20=request.form.get('name_20'),
                short_name=request.form.get('short_name'),
                team_url=request.form.get('team_url'),
                logo_path=request.form.get('logo_path'),
                uniform={'home': uniform_home, 'away': uniform_away}
            )

            flash(f'Zaktualizowano zespół: {team.name}', 'success')
            return redirect(url_for('view_team', team_id=team.id))

        except Exception as e:
            logger.error(f"Error updating team: {e}")
            flash(f'Błąd podczas aktualizacji zespołu: {str(e)}', 'error')

    return render_template('teams/edit.html', team=team, logos=logos)


@current_app.route('/teams/<int:team_id>/delete', methods=['POST'])
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

@current_app.route('/games/scrape', methods=['GET', 'POST'])
@current_app.route('/leagues/<int:league_id>/games/scrape', methods=['GET', 'POST'])
def scrape_games(league_id=None):
    """Scrape games from NALF league pages (async)"""
    selected_league_id = int(request.form.get('league_id', league_id or 0))
    league = league_manager.get_league_by_id(selected_league_id)
    teams = Team.query.order_by(Team.name).all()
    if request.method == 'POST':
        try:
            
            # Check if scraping already in progress
            if game_scraper_manager.is_scraping_in_progress():
                flash('Scrapowanie już trwa. Poczekaj na zakończenie.', 'info')
                return redirect(url_for('game_scrape_status'))

            # Get URLs from form (comma or newline separated)
            urls = []
            urls.append(league.games_url)

            if not urls:
                flash('Podaj przynajmniej jeden URL do tabeli ligi', 'error')
                return render_template('games/scrape.html')
            
            print(f'urls: {urls}')

            # Start async scraping
            if game_scraper_manager.scrape_games_async(urls):
                flash(f'Rozpoczęto scrapowanie {len(urls)} lig w tle...', 'info')
                return redirect(url_for('game_scrape_status'))
            else:
                flash('Nie udało się rozpocząć scrapowania', 'error')

        except Exception as e:
            logger.error(f"Error starting scraping: {e}")
            flash(f'Błąd podczas rozpoczynania scrapowania: {str(e)}', 'error')

    # Default URLs for quick scraping
    default_urls = [
        'https://nalffutsal.pl/?page_id=34',  # Dywizja A
        'https://nalffutsal.pl/?page_id=52',  # Dywizja B
        'https://nalffutsal.pl/?page_id=32',  # Puchar Ligi
    ]

    scraping_status = game_scraper_manager.get_scraping_status()

    return render_template('games/scrape.html',
                           default_urls=default_urls,
                           league=league,
                           scraping_status=scraping_status)

@current_app.route('/game/scrape/status')
def game_scrape_status():
    """Show scraping status page"""
    status = game_scraper_manager.get_scraping_status()
    stats = game_scraper_manager.get_statistics()

    return render_template('games/scrape_status.html',
                           status=status,
                           stats=stats)

@current_app.route('/games/scrape/clear-status', methods=['POST'])
def clear_games_scrape_status():
    """Clear scraping status"""
    game_scraper_manager.clear_scraping_status()
    flash('Wyczyszczono status scrapowania', 'info')
    return redirect(url_for('list_games'))

@current_app.route('/teams/scrape', methods=['GET', 'POST'])
def scrape_teams():
    """Scrape teams from NALF league pages (async)"""
    if request.method == 'POST':
        try:
            # Check if scraping already in progress
            if team_scraper_manager.is_scraping_in_progress():
                flash('Scrapowanie już trwa. Poczekaj na zakończenie.', 'info')
                return redirect(url_for('teams_scrape_status'))

            # Get URLs from form (comma or newline separated)
            urls_input = request.form.get('league_urls', '')
            urls = [url.strip() for url in urls_input.replace('\n', ',').split(',') if url.strip()]

            if not urls:
                flash('Podaj przynajmniej jeden URL do tabeli ligi', 'error')
                return render_template('teams/scrape.html')

            # Start async scraping
            if team_scraper_manager.scrape_leagues_async(urls):
                flash(f'Rozpoczęto scrapowanie {len(urls)} lig w tle...', 'info')
                return redirect(url_for('teams_scrape_status'))
            else:
                flash('Nie udało się rozpocząć scrapowania', 'error')

        except Exception as e:
            logger.error(f"Error starting scraping: {e}")
            flash(f'Błąd podczas rozpoczynania scrapowania: {str(e)}', 'error')

    # Default URLs for quick scraping
    default_urls = [
        'https://nalffutsal.pl/?page_id=16',  # Ekstraklasa
        'https://nalffutsal.pl/?page_id=36',  # I Liga
    ]

    scraping_status = team_scraper_manager.get_scraping_status()

    return render_template('teams/scrape.html',
                           default_urls=default_urls,
                           scraping_status=scraping_status)


@current_app.route('/teams/scrape/status')
def teams_scrape_status():
    """Show scraping status page"""
    status = team_scraper_manager.get_scraping_status()
    stats = team_scraper_manager.get_statistics()

    return render_template('teams/scrape_status.html',
                           status=status,
                           stats=stats)


@current_app.route('/teams/scrape/clear-status', methods=['POST'])
def clear_teams_scrape_status():
    """Clear scraping status"""
    team_scraper_manager.clear_scraping_status()
    flash('Wyczyszczono status scrapowania', 'info')
    return redirect(url_for('list_teams'))


@current_app.route('/teams/pending')
def pending_teams():
    """List pending teams from scraping that need completion"""
    pending = team_scraper_manager.get_pending_teams()
    logos = team_manager.get_all_logos()

    if not pending:
        flash('Brak zespołów do uzupełnienia', 'info')
        return redirect(url_for('list_teams'))

    return render_template('teams/pending.html', pending_teams=pending, logos=logos)


@current_app.route('/teams/complete/<path:team_url>', methods=['GET', 'POST'])
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
                name_20=request.form['name_20'],
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


@current_app.route('/teams/pending/clear', methods=['POST'])
def clear_pending():
    """Clear all pending teams"""
    team_scraper_manager.clear_pending_teams()
    flash('Wyczyszczono listę zespołów do uzupełnienia', 'info')
    return redirect(url_for('list_teams'))


# =========================
# API Endpoints
# =========================

@current_app.route('/api/teams')
def api_list_teams():
    """API: List all teams"""
    teams = team_manager.get_all_teams()
    return jsonify({
        'teams': [team.to_dict() for team in teams]
    })


@current_app.route('/api/teams/<int:team_id>')
def api_get_team(team_id):
    """API: Get single team"""
    team = team_manager.get_team_by_id(team_id)

    if not team:
        return jsonify({'error': 'Team not found'}), 404

    return jsonify(team.to_dict())


@current_app.route('/api/teams/stats')
def api_stats():
    """API: Get team statistics"""
    return jsonify(team_scraper_manager.get_statistics())


@current_app.route('/api/teams/scraping/status')
def api_teams_scrape_status():
    """API: Get scraping status"""
    status = team_scraper_manager.get_scraping_status()
    return jsonify(status)


@current_app.route('/teams/scraping/stop', methods=['POST'])
def stop_scraping():
    if team_scraper_manager.stop_scraping():
        return jsonify({'success': True, 'message': 'Stop requested'})
    return jsonify({'success': False, 'message': 'No scraping in progress'})

"""
API Endpoint to add to routes.py
Place this at the end of the API endpoints section
"""

@current_app.route('/api/settings/current-timers')
def api_current_timers():
    """
    Get current timers from Settings
    
    Returns JSON:
    {
        "main": {
            "timer_id": "...",
            "state": "...",
            ...
        },
        "penalties": [...]
    }
    """
    from app.models.settings import Settings
    
    timers = Settings.get_current_timers()
    return jsonify(timers)


@current_app.route('/api/settings/current-timers/clear', methods=['POST'])
def api_clear_current_timers():
    """
    Clear all current timers (for testing/reset)
    """
    from app.models.settings import Settings
    
    Settings.clear_timers()
    return jsonify({
        'success': True,
        'message': 'Timers cleared'
    })

# @current_app.route('/api/settings')
# def api_get_settings():
#     """
#     Get complete settings including current period, game and timers
    
#     Returns JSON:
#     {
#         "current_season_id": int or null,
#         "current_game_id": int or null,
#         "current_period_id": int or null,
#         "current_timers": {
#             "main": {...} or null,
#             "penalties": [...]
#         },
#         "period": {
#             "id": int,
#             "description": str,
#             "main_timer_name": str,
#             ...
#         } or null,
#         "game": {
#             "id": int,
#             ...
#         } or null
#     }
#     """
#     from app.models.settings import Settings
#     from app.models.period import Period
#     from app.models.game import Game
    
#     settings = Settings.get_settings()
#     current_timers = settings.get_current_timers()
    
#     # Get period details if exists
#     period_data = None
#     if settings.current_period_id:
#         period = Period.query.get(settings.current_period_id)
#         if period:
#             period_data = {
#                 "id": period.id,
#                 "description": period.description,
#                 "period_order": period.period_order,
#                 "main_timer_name": period.main_timer_name,
#                 "initial_time": period.initial_time,
#                 "limit": period.limit,
#                 "pause_at_limit": period.pause_at_limit,
#                 "status": period.status
#             }
    
#     # Get game details if exists
#     game_data = None
#     if settings.current_game_id:
#         game = Game.query.get(settings.current_game_id)
#         if game:
#             game_data = {
#                 "id": game.id,
#                 # Add other game fields as needed
#             }
    
#     return jsonify({
#         "current_season_id": settings.current_season_id,
#         "current_game_id": settings.current_game_id,
#         "current_period_id": settings.current_period_id,
#         "current_timers": current_timers,
#         "period": period_data,
#         "game": game_data
#     })

@current_app.route('/api/settings')
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
    from app.models.settings import Settings
    from app.models.period import Period
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

@current_app.route('/api/scoreboard-state', methods=['GET', 'POST'])
def get_scoreboard_state():
    from app.models.settings import Settings
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
    
    return jsonify({
        'is_reversed': settings.is_scoreboard_reversed
    })

# # Endpoint do zapisywania stanu
# @app.route('/api/scoreboard-state', methods=['POST'])
# def update_scoreboard_state():
#     data = request.get_json()
#     setting = Setting.query.get(1)
    
#     if setting:
#         setting.is_scoreboard_reversed = data.get('is_reversed', False)
#         setting.updated_at = datetime.utcnow()
#     else:
#         setting = Setting(
#             id=1, 
#             is_scoreboard_reversed=data.get('is_reversed', False)
#         )
#         db.session.add(setting)
    
#     db.session.commit()
    
#     return jsonify({'success': True, 'is_reversed': setting.is_scoreboard_reversed})
