"""Routes for Season, League and Game CRUD operations"""
from flask import render_template, jsonify, current_app, flash, redirect, url_for, request
from app.managers.season_manager import SeasonManager
from app.managers.league_manager import LeagueManager
from app.managers.game_manager import GameManager
from app.models.stadium import Stadium
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

@current_app.route('/seasons/')
def list_seasons():
    """List all seasons"""
    seasons = season_manager.get_all_seasons()
    return render_template('seasons/list.html', seasons=seasons)


@current_app.route('/seasons/<int:season_id>')
def view_season(season_id):
    """View season details with statistics"""
    stats = season_manager.get_season_statistics(season_id)
    
    if not stats:
        flash('Nie znaleziono sezonu', 'error')
        return redirect(url_for('list_seasons'))
    
    return render_template('seasons/view.html', stats=stats)


@current_app.route('/seasons/create', methods=['GET', 'POST'])
def create_season():
    """Create new season"""
    if request.method == 'POST':
        try:
            season = season_manager.create_season(
                number=int(request.form['number']),
                name=request.form['name']
            )
            
            flash(f'Utworzono sezon: {season.name}', 'success')
            return redirect(url_for('view_season', season_id=season.id))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Error creating season: {e}")
            flash(f'Błąd podczas tworzenia sezonu: {str(e)}', 'error')
    
    return render_template('seasons/create.html')


@current_app.route('/seasons/<int:season_id>/edit', methods=['GET', 'POST'])
def edit_season(season_id):
    """Edit existing season"""
    season = season_manager.get_season_by_id(season_id)
    
    if not season:
        flash('Nie znaleziono sezonu', 'error')
        return redirect(url_for('list_seasons'))
    
    if request.method == 'POST':
        try:
            season_manager.update_season(
                season_id=season_id,
                number=int(request.form.get('number')) if request.form.get('number') else None,
                name=request.form.get('name')
            )
            
            flash(f'Zaktualizowano sezon: {season.name}', 'success')
            return redirect(url_for('view_season', season_id=season.id))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Error updating season: {e}")
            flash(f'Błąd podczas aktualizacji sezonu: {str(e)}', 'error')
    
    return render_template('seasons/edit.html', season=season)


@current_app.route('/seasons/<int:season_id>/delete', methods=['POST'])
def delete_season(season_id):
    """Delete season"""
    season = season_manager.get_season_by_id(season_id)
    
    if not season:
        flash('Nie znaleziono sezonu', 'error')
        return redirect(url_for('list_seasons'))
    
    season_name = season.name
    
    try:
        if season_manager.delete_season(season_id):
            flash(f'Usunięto sezon: {season_name}', 'success')
        else:
            flash('Błąd podczas usuwania sezonu', 'error')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('list_seasons'))


# =========================
# LEAGUE ROUTES
# =========================

@current_app.route('/leagues/')
@current_app.route('/seasons/<int:season_id>/leagues/')
def list_leagues(season_id=None):
    """List all leagues, optionally filtered by season"""
    leagues = league_manager.get_all_leagues(season_id=season_id)
    season = season_manager.get_season_by_id(season_id) if season_id else None
    
    return render_template('leagues/list.html', 
                          leagues=leagues, 
                          season=season)


@current_app.route('/leagues/<int:league_id>')
def view_league(league_id):
    """View league details with statistics"""
    stats = league_manager.get_league_statistics(league_id)
    
    if not stats:
        flash('Nie znaleziono ligi', 'error')
        return redirect(url_for('list_leagues'))
    
    return render_template('leagues/view.html', stats=stats)


@current_app.route('/leagues/create', methods=['GET', 'POST'])
@current_app.route('/seasons/<int:season_id>/leagues/create', methods=['GET', 'POST'])
def create_league(season_id=None):
    """Create new league"""
    seasons = season_manager.get_all_seasons()
    
    if request.method == 'POST':
        try:
            selected_season_id = int(request.form.get('season_id', season_id or 0))
            
            league = league_manager.create_league(
                season_id=selected_season_id,
                name=request.form['name'],
                games_url=request.form['games_url'],
                scorers_url=request.form['scorers_url'],
                assists_url=request.form['assists_url'],
                canadian_url=request.form['canadian_url'],
                table_url=request.form.get('table_url', '')
            )
            
            flash(f'Utworzono ligę: {league.name}', 'success')
            return redirect(url_for('view_league', league_id=league.id))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Error creating league: {e}")
            flash(f'Błąd podczas tworzenia ligi: {str(e)}', 'error')
    
    return render_template('leagues/create.html', 
                          seasons=seasons, 
                          selected_season_id=season_id)


@current_app.route('/leagues/<int:league_id>/edit', methods=['GET', 'POST'])
def edit_league(league_id):
    """Edit existing league"""
    league = league_manager.get_league_by_id(league_id)
    
    if not league:
        flash('Nie znaleziono ligi', 'error')
        return redirect(url_for('list_leagues'))
    
    if request.method == 'POST':
        try:
            league_manager.update_league(
                league_id=league_id,
                name=request.form.get('name'),
                games_url=request.form.get('games_url'),
                table_url=request.form.get('table_url'),
                scorers_url=request.form.get('scorers_url'),
                assists_url=request.form.get('assists_url'),
                canadian_url=request.form.get('canadian_url')
            )
            
            flash(f'Zaktualizowano ligę: {league.name}', 'success')
            return redirect(url_for('view_league', league_id=league.id))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Error updating league: {e}")
            flash(f'Błąd podczas aktualizacji ligi: {str(e)}', 'error')
    
    return render_template('leagues/edit.html', league=league)


@current_app.route('/leagues/<int:league_id>/delete', methods=['POST'])
def delete_league(league_id):
    """Delete league"""
    league = league_manager.get_league_by_id(league_id)
    
    if not league:
        flash('Nie znaleziono ligi', 'error')
        return redirect(url_for('list_leagues'))
    
    league_name = league.name
    season_id = league.season_id
    
    try:
        if league_manager.delete_league(league_id):
            flash(f'Usunięto ligę: {league_name}', 'success')
            return redirect(url_for('list_leagues', season_id=season_id))
        else:
            flash('Błąd podczas usuwania ligi', 'error')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('list_leagues'))


# =========================
# LEAGUE TEAMS MANAGEMENT
# =========================

@current_app.route('/leagues/<int:league_id>/teams')
def league_teams(league_id):
    """Manage teams in a league"""
    league = league_manager.get_league_by_id(league_id)
    
    if not league:
        flash('Nie znaleziono ligi', 'error')
        return redirect(url_for('list_leagues'))
    
    teams = league_manager.get_league_teams(league_id)
    available_teams = league_manager.get_available_teams(league_id)
    
    return render_template('leagues/teams.html',
                          league=league,
                          teams=teams,
                          available_teams=available_teams)


@current_app.route('/leagues/<int:league_id>/teams/add', methods=['POST'])
def add_team_to_league(league_id):
    """Add team to league"""
    try:
        team_id = int(request.form['team_id'])
        group_nr = int(request.form.get('group_nr', 1))
        
        league_manager.add_team_to_league(league_id, team_id, group_nr)
        flash('Dodano zespół do ligi', 'success')
        
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        logger.error(f"Error adding team to league: {e}")
        flash(f'Błąd: {str(e)}', 'error')
    
    return redirect(url_for('league_teams', league_id=league_id))


@current_app.route('/leagues/<int:league_id>/teams/<int:team_id>/remove', methods=['POST'])
def remove_team_from_league(league_id, team_id):
    """Remove team from league"""
    try:
        if league_manager.remove_team_from_league(league_id, team_id):
            flash('Usunięto zespół z ligi', 'success')
        else:
            flash('Błąd podczas usuwania zespołu', 'error')
            
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        logger.error(f"Error removing team from league: {e}")
        flash(f'Błąd: {str(e)}', 'error')
    
    return redirect(url_for('league_teams', league_id=league_id))


@current_app.route('/leagues/<int:league_id>/teams/<int:team_id>/group', methods=['POST'])
def update_team_group(league_id, team_id):
    """Update team's group in league"""
    try:
        group_nr = int(request.form['group_nr'])
        
        if league_manager.update_team_group(league_id, team_id, group_nr):
            flash('Zaktualizowano grupę zespołu', 'success')
        else:
            flash('Błąd podczas aktualizacji grupy', 'error')
            
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        logger.error(f"Error updating team group: {e}")
        flash(f'Błąd: {str(e)}', 'error')
    
    return redirect(url_for('league_teams', league_id=league_id))


# =========================
# MATCH ROUTES
# =========================

# @current_app.route('/games/')
@current_app.route('/leagues/<int:league_id>/games/')
def league_games(league_id=None):
    """List all games, optionally filtered by league"""
    games = game_manager.get_all_games(league_id=league_id)
    league = league_manager.get_league_by_id(league_id) if league_id else None
    
    return render_template('games/list.html',
                          games=games,
                          league=league)


@current_app.route('/games/<int:game_id>')
def view_game(game_id):
    """View game details"""
    game = game_manager.get_game_by_id(game_id)
    
    if not game:
        flash('Nie znaleziono meczu', 'error')
        return redirect(url_for('list_games'))
    
    return render_template('games/view.html', game=game)


@current_app.route('/games/create', methods=['GET', 'POST'])
@current_app.route('/leagues/<int:league_id>/games/create', methods=['GET', 'POST'])
def create_game(league_id=None):
    """Create new game"""
    leagues = league_manager.get_all_leagues()
    teams = Team.query.order_by(Team.name).all()
    stadiums = Stadium.query.order_by(Stadium.city, Stadium.name).all()
    
    if request.method == 'POST':
        try:
            selected_league_id = int(request.form.get('league_id', league_id or 0))
            
            # Parse date if provided
            game_date = None
            if request.form.get('date') and request.form.get('time'):
                date_str = f"{request.form['date']} {request.form['time']}"
                game_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            
            game = game_manager.create_game(
                home_team_id=int(request.form['home_team_id']),
                away_team_id=int(request.form['away_team_id']),
                league_id=selected_league_id,
                stadium_id=int(request.form['stadium_id']),
                round_number=int(request.form['round']),
                group_nr=int(request.form.get('group_nr', 1)),
                date=game_date
            )
            
            flash(f'Utworzono mecz', 'success')
            return redirect(url_for('view_game', game_id=game.id))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Error creating game: {e}")
            flash(f'Błąd podczas tworzenia meczu: {str(e)}', 'error')
    
    return render_template('games/create.html',
                          leagues=leagues,
                          teams=teams,
                          stadiums=stadiums,
                          selected_league_id=league_id)


@current_app.route('/games/<int:game_id>/edit', methods=['GET', 'POST'])
def edit_game(game_id):
    """Edit existing game"""
    game = game_manager.get_game_by_id(game_id)
    
    if not game:
        flash('Nie znaleziono meczu', 'error')
        return redirect(url_for('list_games'))
    
    teams = Team.query.order_by(Team.name).all()
    stadiums = Stadium.query.order_by(Stadium.city, Stadium.name).all()
    
    if request.method == 'POST':
        try:
            # Parse date if provided
            game_date = None
            if request.form.get('date') and request.form.get('time'):
                date_str = f"{request.form['date']} {request.form['time']}"
                game_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            
            game_manager.update_game(
                game_id=game_id,
                home_team_id=int(request.form.get('home_team_id')) if request.form.get('home_team_id') else None,
                away_team_id=int(request.form.get('away_team_id')) if request.form.get('away_team_id') else None,
                home_team_goals=int(request.form.get('home_team_goals')) if request.form.get('home_team_goals') else None,
                away_team_goals=int(request.form.get('away_team_goals')) if request.form.get('away_team_goals') else None,
                is_home_team_lost_by_wo=int(request.form.get('is_home_team_lost_by_wo')) if request.form.get('is_home_team_lost_by_wo') else None,
                is_away_team_lost_by_wo=int(request.form.get('is_away_team_lost_by_wo')) if request.form.get('is_away_team_lost_by_wo') else None,
                stadium_id=int(request.form.get('stadium_id')) if request.form.get('stadium_id') else None,
                date=game_date,
                round_number=int(request.form.get('round')) if request.form.get('round') else None,
                group_nr=int(request.form.get('group_nr')) if request.form.get('group_nr') else None
            )
            
            flash(f'Zaktualizowano mecz', 'success')
            return redirect(url_for('view_game', game_id=game.id))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Error updating game: {e}")
            flash(f'Błąd podczas aktualizacji meczu: {str(e)}', 'error')
    
    return render_template('games/edit.html',
                          game=game,
                          teams=teams,
                          stadiums=stadiums)


@current_app.route('/games/<int:game_id>/delete', methods=['POST'])
def delete_game(game_id):
    """Delete game"""
    game = game_manager.get_game_by_id(game_id)
    
    if not game:
        flash('Nie znaleziono meczu', 'error')
        return redirect(url_for('list_games'))
    
    league_id = game.league_id
    
    try:
        if game_manager.delete_game(game_id):
            flash('Usunięto mecz', 'success')
            return redirect(url_for('list_games', league_id=league_id))
        else:
            flash('Błąd podczas usuwania meczu', 'error')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('list_games'))


# =========================
# API ENDPOINTS
# =========================

@current_app.route('/api/seasons')
def api_list_seasons():
    """API: List all seasons"""
    seasons = season_manager.get_all_seasons()
    return jsonify({
        'seasons': [season.to_dict() for season in seasons]
    })


@current_app.route('/api/seasons/<int:season_id>')
def api_get_season(season_id):
    """API: Get season with statistics"""
    stats = season_manager.get_season_statistics(season_id)
    
    if not stats:
        return jsonify({'error': 'Season not found'}), 404
    
    return jsonify(stats)


@current_app.route('/api/leagues')
def api_list_leagues():
    """API: List all leagues"""
    season_id = request.args.get('season_id', type=int)
    leagues = league_manager.get_all_leagues(season_id=season_id)
    
    return jsonify({
        'leagues': [league.to_dict() for league in leagues]
    })


@current_app.route('/api/leagues/<int:league_id>')
def api_get_league(league_id):
    """API: Get league with statistics"""
    stats = league_manager.get_league_statistics(league_id)
    
    if not stats:
        return jsonify({'error': 'League not found'}), 404
    
    return jsonify(stats)


@current_app.route('/api/games')
def api_list_games():
    """API: List all games"""
    league_id = request.args.get('league_id', type=int)
    team_id = request.args.get('team_id', type=int)
    status = request.args.get('status', type=int)
    
    games = game_manager.get_all_games(
        league_id=league_id,
        team_id=team_id,
        status=status
    )
    
    return jsonify({
        'games': [game.to_dict() for game in games]
    })


@current_app.route('/api/games/<int:game_id>')
def api_get_game(game_id):
    """API: Get single game"""
    game = game_manager.get_game_by_id(game_id)
    
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    
    return jsonify(game.to_dict())
