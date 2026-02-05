"""All routes - MINIMAL"""
from flask import render_template, jsonify, current_app, flash, redirect, url_for, request
# from app.models import Plugin

from app.managers.team_manager import TeamManager
from app.managers.scraper_manager import ScraperManager
from app.models.team import Team
import logging
import time
import os


logger = logging.getLogger(__name__)

team_manager = TeamManager()
scraper_manager = ScraperManager()

@current_app.route('/')
def index():
    """Main dashboard"""
    # try:
    #     plugins = Plugin.query.order_by(Plugin.startup_priority).all()
    # except:
    #     plugins = []
    plugins = current_app.config['REQUIRED_PLUGINS']

    return render_template('index.html',
                           plugins=plugins,
                           module_name=current_app.config['MODULE_NAME'])


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


@current_app.route('/teams/')
def list_teams():
    """List all teams in database"""
    teams = team_manager.get_all_teams()
    stats = scraper_manager.get_statistics()
    scraping_status = scraper_manager.get_scraping_status()

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
            team = team_manager.create_team(
                name=request.form['name'],
                name_20=request.form['name_20'],
                short_name=request.form['short_name'],
                team_url=request.form['team_url'],
                logo_path=request.form.get('logo_path', 'static/images/logos/default.png')
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
            team_manager.update_team(
                team_id=team_id,
                name=request.form.get('name'),
                name_20=request.form.get('name_20'),
                short_name=request.form.get('short_name'),
                team_url=request.form.get('team_url'),
                logo_path=request.form.get('logo_path')
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

@current_app.route('/teams/scrape', methods=['GET', 'POST'])
def scrape_teams():
    """Scrape teams from NALF league pages (async)"""
    if request.method == 'POST':
        try:
            # Check if scraping already in progress
            if scraper_manager.is_scraping_in_progress():
                flash('Scrapowanie już trwa. Poczekaj na zakończenie.', 'info')
                return redirect(url_for('scrape_status'))

            # Get URLs from form (comma or newline separated)
            urls_input = request.form.get('league_urls', '')
            urls = [url.strip() for url in urls_input.replace('\n', ',').split(',') if url.strip()]

            if not urls:
                flash('Podaj przynajmniej jeden URL do tabeli ligi', 'error')
                return render_template('teams/scrape.html')

            # Start async scraping
            if scraper_manager.scrape_leagues_async(urls):
                flash(f'Rozpoczęto scrapowanie {len(urls)} lig w tle...', 'info')
                return redirect(url_for('scrape_status'))
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

    scraping_status = scraper_manager.get_scraping_status()

    return render_template('teams/scrape.html',
                           default_urls=default_urls,
                           scraping_status=scraping_status)


@current_app.route('/teams/scrape/status')
def scrape_status():
    """Show scraping status page"""
    status = scraper_manager.get_scraping_status()
    stats = scraper_manager.get_statistics()

    return render_template('teams/scrape_status.html',
                           status=status,
                           stats=stats)


@current_app.route('/teams/scrape/clear-status', methods=['POST'])
def clear_scrape_status():
    """Clear scraping status"""
    scraper_manager.clear_scraping_status()
    flash('Wyczyszczono status scrapowania', 'info')
    return redirect(url_for('list_teams'))


@current_app.route('/teams/pending')
def pending_teams():
    """List pending teams from scraping that need completion"""
    pending = scraper_manager.get_pending_teams()
    logos = team_manager.get_all_logos()

    if not pending:
        flash('Brak zespołów do uzupełnienia', 'info')
        return redirect(url_for('list_teams'))

    return render_template('teams/pending.html', pending_teams=pending, logos=logos)


@current_app.route('/teams/complete/<path:team_url>', methods=['GET', 'POST'])
def complete_team(team_url):
    """Complete scraped team with additional data"""
    # Get pending team
    pending_team = scraper_manager.get_pending_team_by_url(team_url)
    logos = team_manager.get_all_logos()

    if not pending_team:
        flash('Nie znaleziono zespołu do uzupełnienia', 'error')
        return redirect(url_for('pending_teams'))

    if request.method == 'POST':
        try:
            team = scraper_manager.complete_team_from_scraping(
                team_url=team_url,
                name_20=request.form['name_20'],
                short_name=request.form['short_name'],
                logo_path=request.form.get('logo_path', 'static/images/logos/default.png')
            )

            if team:
                flash(f'Dodano zespół: {team.name}', 'success')

                # Check if there are more pending teams
                remaining = len(scraper_manager.get_pending_teams())
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
    scraper_manager.clear_pending_teams()
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
    return jsonify(scraper_manager.get_statistics())


@current_app.route('/api/teams/scraping/status')
def api_scrape_status():
    """API: Get scraping status"""
    status = scraper_manager.get_scraping_status()
    return jsonify(status)


@current_app.route('/teams/scraping/stop', methods=['POST'])
def stop_scraping():
    if scraper_manager.stop_scraping():
        return jsonify({'success': True, 'message': 'Stop requested'})
    return jsonify({'success': False, 'message': 'No scraping in progress'})