"""Match Manager - Manages game logic"""
from flask import current_app
from app.models import Game, Settings
from app.extensions import db
from datetime import datetime


class CurrentGameManager:
    """Manages game operations"""

    def __init__(self, hub_client):
        self.hub_client = hub_client
        self.current_game_id = None

    def get_current_game(self):
        """Get current active game"""
        settings = Settings.query.get(id=1).first()
        self.current_game_id = settings.current_game_id

        game = Game.query.get(self.current_game_id)

        return game

    def start_game(self, game_id=None):
        """Start a game"""
        if game_id:
            game = Game.query.get(game_id)
        else:
            # Get next scheduled game
            game = Game.query.filter_by(status='scheduled').first()

        if not game:
            return {'error': 'No game to start'}

        game.start_game()
        self.current_game_id = game.id

        current_app.logger.info(f"🎮 Game started: {game.home_team.name} vs {game.away_team.name}")

        # Broadcast to plugins
        self.hub_client.broadcast('game_started', {
            'game_id': game.id,
            'home_team': game.home_team.name,
            'away_team': game.away_team.name
        })

        from app.schemas import game_schema
        return {
            'status': 'game_started',
            'game': game_schema.dump(game)
        }

    def finish_game(self):
        """Finish current game"""
        game = self.get_current_game()
        if not game:
            return {'error': 'No active game'}

        game.finish_game()

        current_app.logger.info(
            f"🏁 Game finished: {game.home_team.name} {game.score_home} - {game.score_away} {game.away_team.name}")

        # Broadcast
        self.hub_client.broadcast('game_finished', {
            'game_id': game.id,
            'final_score': {
                'home': game.score_home,
                'away': game.score_away
            }
        })

        self.current_game_id = None

        from app.schemas import game_schema
        return {
            'status': 'game_finished',
            'game': game_schema.dump(game)
        }

    def score_goal(self, team_type, player_name=None):
        """Score a goal"""
        game = self.get_current_game()
        if not game:
            return {'error': 'No active game'}

        if team_type not in ['home', 'away']:
            return {'error': 'Invalid team type'}

        # Update score
        game.score_goal(team_type)

        # Create goal record
        goal = Goal(
            game_id=game.id,
            team_type=team_type,
            player_name=player_name,
            half=game.half,
            scored_at=datetime.utcnow()
        )
        db.session.add(goal)
        db.session.commit()

        team_name = game.home_team.name if team_type == 'home' else game.away_team.name
        current_app.logger.info(f"⚽ GOAL! {team_name} - Score: {game.score_home}:{game.score_away}")

        # Broadcast to plugins
        self.hub_client.broadcast('goal_scored', {
            'game_id': game.id,
            'team': team_type,
            'team_name': team_name,
            'player_name': player_name,
            'score': {
                'home': game.score_home,
                'away': game.score_away
            }
        })

        from app.schemas import game_schema
        return {
            'status': 'goal_scored',
            'team': team_type,
            'score': {
                'home': game.score_home,
                'away': game.score_away
            },
            'game': game_schema.dump(game)
        }

    def switch_half(self):
        """Switch to second half"""
        game = self.get_current_game()
        if not game:
            return {'error': 'No active game'}

        game.half = 2
        db.session.commit()

        current_app.logger.info(f"🔄 Switching to second half")

        # Broadcast
        self.hub_client.broadcast('game_halftime', {
            'game_id': game.id,
            'half': 2
        })

        return {'status': 'second_half_started', 'half': 2}

    def get_game_data(self):
        """Get current game data for UI"""
        game = self.get_current_game()
        if not game:
            return None

        from app.schemas import game_schema
        return game_schema.dump(game)
