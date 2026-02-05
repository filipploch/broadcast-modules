"""All routes - MINIMAL"""
from flask import render_template, jsonify, current_app, Blueprint
# from app.models import Plugin

app_bp = Blueprint('app', __name__, url_prefix='/')


@app_bp.route('/')
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


@app_bp.route('/overlay/scoreboard')


def overlay_scoreboard():
    """Scoreboard overlay"""
    return render_template('overlays/scoreboard.html')


@app_bp.route('/api/status')


def api_status():
    """Application status"""
    return jsonify({
        'status': 'running',
        'module_id': current_app.config['MODULE_ID']
    })
