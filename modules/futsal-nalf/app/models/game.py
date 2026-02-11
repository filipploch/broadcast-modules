"""Game model - Football games"""
from app.extensions import db
from datetime import datetime


class Game(db.Model):
    """Football game/match"""
    __tablename__ = 'games'

    # Status constants
    STATUS_NOT_STARTED = 0
    STATUS_PENDING = 1
    STATUS_FINISHED = 2

    # Walkover constants
    WALKOVER_SCORE = 5

    id = db.Column(db.Integer, primary_key=True)
    foreign_id = db.Column(db.String(500), nullable=True)

    # Teams
    home_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)
    away_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)

    # Scores
    home_team_goals = db.Column(db.Integer, nullable=True)
    away_team_goals = db.Column(db.Integer, nullable=True)
    home_team_fouls = db.Column(db.Integer, nullable=False, default=0)
    away_team_fouls = db.Column(db.Integer, nullable=False, default=0)

    # Walkover - nowe pola
    is_home_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)
    is_away_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)

    # Status (0 = not started, 1 = pending, 2 = finished)
    status = db.Column(db.Integer, nullable=False, default=STATUS_NOT_STARTED, index=True)

    # League and group
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False, index=True)
    group_nr = db.Column(db.Integer, nullable=False, default=1)

    # Stadium
    stadium_id = db.Column(db.Integer, db.ForeignKey('stadiums.id'), nullable=False, default=1)

    # Schedule
    date = db.Column(db.DateTime, nullable=True, index=True)
    round = db.Column(db.Integer, nullable=False, index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships defined via backref in Team, League, Stadium
    # New relationships
    periods = db.relationship('Period', backref='game', lazy='dynamic', cascade='all, delete-orphan', order_by='Period.period_order')
    game_cameras = db.relationship('GameCamera', backref='game', lazy='dynamic', cascade='all, delete-orphan')
    penalty = db.relationship('Penalty', backref='game', uselist=False, cascade='all, delete-orphan')  # One-to-one
    player_games = db.relationship('PlayerGame', backref='game', lazy='dynamic', cascade='all, delete-orphan')
    game_events = db.relationship('GameEvent', backref='game', lazy='dynamic', cascade='all, delete-orphan', order_by='GameEvent.time')
    game_referees = db.relationship('GameReferee', backref='game', lazy='dynamic', cascade='all, delete-orphan')

    # Indexes
    __table_args__ = (
        db.Index('ix_game_league_round', 'league_id', 'round'),
        db.Index('ix_game_date_status', 'date', 'status'),
    )

    def __repr__(self):
        return f'<Game {self.id}: {self.home_team.short_name if self.home_team else "?"} vs {self.away_team.short_name if self.away_team else "?"}>'

    @property
    def is_walkover(self):
        """Check if game ended with any walkover"""
        return self.is_home_team_lost_by_wo or self.is_away_team_lost_by_wo

    @property
    def is_double_walkover(self):
        """Check if both teams lost by walkover"""
        return self.is_home_team_lost_by_wo and self.is_away_team_lost_by_wo

    @property
    def is_finished(self):
        """Check if game is finished"""
        return self.status == self.STATUS_FINISHED

    @property
    def is_live(self):
        """Check if game is currently live"""
        return self.status == self.STATUS_PENDING

    @property
    def score_string(self):
        """Get formatted score string"""
        if self.home_team_goals is None or self.away_team_goals is None:
            return "- : -"

        score = f"{self.home_team_goals} : {self.away_team_goals}"

        if self.is_walkover:
            score += " (WO)"

        return score

    @property
    def winner_id(self):
        """Get winner team ID (None if draw or not finished)"""
        if not self.is_finished or self.home_team_goals is None or self.away_team_goals is None:
            return None

        if self.home_team_goals > self.away_team_goals:
            return self.home_team_id
        elif self.away_team_goals > self.home_team_goals:
            return self.away_team_id

        return None  # Draw

    def set_live(self):
        """Mark game as live"""
        self.status = self.STATUS_PENDING
        self.updated_at = datetime.utcnow()

    def set_finished(self):
        """Mark game as finished"""
        self.status = self.STATUS_FINISHED
        self.updated_at = datetime.utcnow()

    def update_score(self, home_goals, away_goals):
        """Update game score"""
        self.home_team_goals = home_goals
        self.away_team_goals = away_goals
        self.updated_at = datetime.utcnow()

    def update_fouls(self, home_fouls, away_fouls):
        """Update fouls count"""
        self.home_team_fouls = home_fouls
        self.away_team_fouls = away_fouls
        self.updated_at = datetime.utcnow()

    def increment_home_goals(self):
        """Increment home team goals"""
        if self.home_team_goals is None:
            self.home_team_goals = 0
        self.home_team_goals += 1
        self.updated_at = datetime.utcnow()

    def increment_away_goals(self):
        """Increment away team goals"""
        if self.away_team_goals is None:
            self.away_team_goals = 0
        self.away_team_goals += 1
        self.updated_at = datetime.utcnow()

    def set_home_walkover_loss(self):
        """Mark home team as lost by walkover"""
        self.is_home_team_lost_by_wo = True
        self.updated_at = datetime.utcnow()

    def set_away_walkover_loss(self):
        """Mark away team as lost by walkover"""
        self.is_away_team_lost_by_wo = True
        self.updated_at = datetime.utcnow()

    def set_double_walkover(self):
        """Mark both teams as lost by walkover"""
        self.is_home_team_lost_by_wo = True
        self.is_away_team_lost_by_wo = True
        self.updated_at = datetime.utcnow()

    def clear_walkovers(self):
        """Clear all walkover flags"""
        self.is_home_team_lost_by_wo = False
        self.is_away_team_lost_by_wo = False
        self.updated_at = datetime.utcnow()

    @property
    def total_periods(self):
        """Get total number of periods for this game"""
        return self.periods.count()

    @property
    def total_cameras(self):
        """Get total number of cameras assigned to this game"""
        return self.game_cameras.count()

    @property
    def has_penalty_shootout(self):
        """Check if game has penalty shootout"""
        return self.penalty is not None

    @property
    def full_score_string(self):
        """
        Get full score string including penalty shootout if exists
        
        Examples:
        - "2 : 1" (regular game)
        - "2 : 2 k. 4:3" (with penalty shootout)
        - "2 : 1 (WO)" (walkover)
        """
        base_score = self.score_string
        
        if self.has_penalty_shootout:
            return f"{base_score} k. {self.penalty.score_string}"
        
        return base_score

    def get_periods_list(self):
        """Get ordered list of periods"""
        return self.periods.order_by('period_order').all()

    def get_cameras_list(self):
        """Get list of cameras with locations"""
        return self.game_cameras.all()

    def get_current_period(self):
        """Get currently active period (status=PENDING)"""
        from app.models.period import Period
        return self.periods.filter_by(status=Period.STATUS_PENDING).first()

    def get_penalty_winner_id(self):
        """Get winner ID from penalty shootout (if exists)"""
        if self.has_penalty_shootout:
            return self.penalty.winner_id
        return None

    def get_players_list(self, team_id=None):
        """
        Get list of players in this game
        
        Args:
            team_id: Optional filter by team
        
        Returns:
            List of PlayerGame objects
        """
        query = self.player_games
        if team_id:
            query = query.filter_by(team_id=team_id)
        return query.all()

    def get_events_list(self, period_id=None, event_id=None):
        """
        Get list of events in this game
        
        Args:
            period_id: Optional filter by period
            event_id: Optional filter by event type
        
        Returns:
            List of GameEvent objects ordered by time
        """
        query = self.game_events
        if period_id:
            query = query.filter_by(period_id=period_id)
        if event_id:
            query = query.filter_by(event_id=event_id)
        return query.order_by('time').all()

    def get_referees_list(self, referee_type=None):
        """
        Get list of referees for this game
        
        Args:
            referee_type: Optional filter by type ("Główny", "Asystent")
        
        Returns:
            List of GameReferee objects
        """
        query = self.game_referees
        if referee_type:
            query = query.filter_by(type=referee_type)
        return query.all()

    @property
    def total_players(self):
        """Get total number of players assigned to this game"""
        return self.player_games.count()

    @property
    def total_events(self):
        """Get total number of events in this game"""
        return self.game_events.count()

    @property
    def total_referees(self):
        """Get total number of referees for this game"""
        return self.game_referees.count()

    def get_team_stats(self, team_id, include_live=False):
        """
        Calculate statistics for a specific team from this game.
        Returns dict with: games, points, wins, draws, loses, goals_scored, goals_lost

        Args:
            team_id: ID of the team to calculate stats for
            include_live: If True, include live games with current score (default: False)

        Returns None if:
        - team is not in this game
        - game is not finished and include_live=False
        - game is not finished/live
        """
        # Check if game is eligible for stats
        if not include_live and not self.is_finished:
            return None

        if include_live and not (self.is_finished or self.is_live):
            return None

        if team_id not in [self.home_team_id, self.away_team_id]:
            return None

        stats = {
            'games': 1,
            'points': 0,
            'wins': 0,
            'draws': 0,
            'loses': 0,
            'goals_scored': 0,
            'goals_lost': 0
        }

        is_home = (team_id == self.home_team_id)
        team_goals = self.home_team_goals if is_home else self.away_team_goals
        opponent_goals = self.away_team_goals if is_home else self.home_team_goals
        team_lost_by_wo = self.is_home_team_lost_by_wo if is_home else self.is_away_team_lost_by_wo
        opponent_lost_by_wo = self.is_away_team_lost_by_wo if is_home else self.is_home_team_lost_by_wo

        # Scenariusz 1: Obie drużyny ukarane walkowerem (5:5, obie liczą jako przegraną)
        if self.is_double_walkover:
            stats['loses'] = 1
            stats['points'] = -1
            stats['goals_lost'] = self.WALKOVER_SCORE
            return stats

        # Scenariusz 2: Tylko ta drużyna przegrała przez walkower
        if team_lost_by_wo:
            stats['loses'] = 1
            stats['points'] = -1
            stats['goals_lost'] = self.WALKOVER_SCORE
            return stats

        # Scenariusz 3: Tylko przeciwnik przegrał przez walkower (wygrana 5:0)
        if opponent_lost_by_wo:
            stats['wins'] = 1
            stats['points'] = 3
            stats['goals_scored'] = self.WALKOVER_SCORE
            return stats

        # Scenariusz 4: Normalny mecz
        if team_goals is not None and opponent_goals is not None:
            stats['goals_scored'] = team_goals
            stats['goals_lost'] = opponent_goals

            if team_goals > opponent_goals:
                # Wygrana
                stats['wins'] = 1
                stats['points'] = 3
            elif team_goals == opponent_goals:
                # Remis
                stats['draws'] = 1
                stats['points'] = 1
            else:
                # Porażka
                stats['loses'] = 1

        return stats

    def get_home_team_stats(self, include_live=False):
        """
        Get statistics for home team from this game

        Args:
            include_live: If True, include live games with current score
        """
        return self.get_team_stats(self.home_team_id, include_live=include_live)

    def get_away_team_stats(self, include_live=False):
        """
        Get statistics for away team from this game

        Args:
            include_live: If True, include live games with current score
        """
        return self.get_team_stats(self.away_team_id, include_live=include_live)

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'foreign_id': self.foreign_id,
            'home_team': {
                'id': self.home_team_id,
                'name': self.home_team.name if self.home_team else None,
                'short_name': self.home_team.short_name if self.home_team else None,
                'goals': self.home_team_goals,
                'fouls': self.home_team_fouls
            },
            'away_team': {
                'id': self.away_team_id,
                'name': self.away_team.name if self.away_team else None,
                'short_name': self.away_team.short_name if self.away_team else None,
                'goals': self.away_team_goals,
                'fouls': self.away_team_fouls
            },
            'is_home_team_lost_by_wo': self.is_home_team_lost_by_wo,
            'is_away_team_lost_by_wo': self.is_away_team_lost_by_wo,
            'is_walkover': self.is_walkover,
            'is_double_walkover': self.is_double_walkover,
            'status': self.status,
            'status_text': self.get_status_text(),
            'league_id': self.league_id,
            'league_name': self.league.name if self.league else None,
            'group_nr': self.group_nr,
            'stadium': {
                'id': self.stadium_id,
                'name': self.stadium.name if self.stadium else None,
                'city': self.stadium.city if self.stadium else None
            },
            'date': self.date.isoformat() if self.date else None,
            'round': self.round,
            'score_string': self.score_string,
            'winner_id': self.winner_id,
            'total_periods': self.total_periods,
            'total_cameras': self.total_cameras,
            'has_penalty_shootout': self.has_penalty_shootout,
            'full_score_string': self.full_score_string,
            'periods': [p.to_dict() for p in self.get_periods_list()],
            'cameras': [gc.to_dict() for gc in self.get_cameras_list()],
            'penalty': self.penalty.to_dict() if self.penalty else None,
            'total_players': self.total_players,
            'total_events': self.total_events,
            'total_referees': self.total_referees,
            'players': [pg.to_dict() for pg in self.get_players_list()],
            'events': [ge.to_dict() for ge in self.get_events_list()],
            'referees': [gr.to_dict() for gr in self.get_referees_list()],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def get_status_text(self):
        """Get human-readable status text"""
        if self.status == self.STATUS_NOT_STARTED:
            return "Not Started"
        elif self.status == self.STATUS_PENDING:
            return "Live"
        elif self.status == self.STATUS_FINISHED:
            return "Finished"
        return "Unknown"

    @classmethod
    def calculate_league_table(cls, league_id, group_nr=1, include_live=False):
        """
        Calculate league table for given league and group.

        Args:
            league_id: League ID to calculate table for
            group_nr: Group number (default: 1)
            include_live: If True, include live games with current score (default: False)

        Returns:
            List of dicts with team statistics, sorted by:
            - points (DESC)
            - goal_difference (DESC)
            - goals_scored (DESC)

        Each dict contains:
            - team_id, team_name, team_short_name
            - games, points, wins, draws, loses
            - goals_scored, goals_lost, goal_difference
        """
        from collections import defaultdict

        # Build query for games
        query = cls.query.filter_by(league_id=league_id, group_nr=group_nr)

        if include_live:
            # Include finished and live games
            query = query.filter(cls.status.in_([cls.STATUS_FINISHED, cls.STATUS_PENDING]))
        else:
            # Only finished games
            query = query.filter_by(status=cls.STATUS_FINISHED)

        games = query.all()

        # Initialize statistics for each team
        stats = defaultdict(lambda: {
            'team_id': None,
            'team_name': None,
            'team_short_name': None,
            'games': 0,
            'points': 0,
            'wins': 0,
            'draws': 0,
            'loses': 0,
            'goals_scored': 0,
            'goals_lost': 0,
            'goal_difference': 0
        })

        # Aggregate statistics from each game
        for game in games:
            home_stats = game.get_home_team_stats(include_live=include_live)
            away_stats = game.get_away_team_stats(include_live=include_live)

            if home_stats:
                for key in home_stats:
                    stats[game.home_team_id][key] += home_stats[key]
                stats[game.home_team_id]['team_id'] = game.home_team_id
                stats[game.home_team_id]['team_name'] = game.home_team.name
                stats[game.home_team_id]['team_short_name'] = game.home_team.short_name

            if away_stats:
                for key in away_stats:
                    stats[game.away_team_id][key] += away_stats[key]
                stats[game.away_team_id]['team_id'] = game.away_team_id
                stats[game.away_team_id]['team_name'] = game.away_team.name
                stats[game.away_team_id]['team_short_name'] = game.away_team.short_name

        # Calculate goal difference
        for team_id in stats:
            stats[team_id]['goal_difference'] = (
                stats[team_id]['goals_scored'] - stats[team_id]['goals_lost']
            )

        # Sort by: points DESC, goal difference DESC, goals scored DESC
        sorted_stats = sorted(
            stats.values(),
            key=lambda x: (x['points'], x['goal_difference'], x['goals_scored']),
            reverse=True
        )

        return sorted_stats

    @classmethod
    def get_league_tables_comparison(cls, league_id, group_nr=1):
        """
        Get comparison of league tables with and without live games.

        Args:
            league_id: League ID
            group_nr: Group number (default: 1)

        Returns:
            Dictionary with:
            - 'current': Table with only finished games
            - 'projected': Table with finished + live games (current scores)
            - 'has_live_games': Boolean indicating if there are live games
        """
        current_table = cls.calculate_league_table(league_id, group_nr, include_live=False)
        projected_table = cls.calculate_league_table(league_id, group_nr, include_live=True)

        # Check if there are any live games
        live_games_count = cls.query.filter_by(
            league_id=league_id,
            group_nr=group_nr,
            status=cls.STATUS_PENDING
        ).count()

        return {
            'current': current_table,
            'projected': projected_table,
            'has_live_games': live_games_count > 0,
            'live_games_count': live_games_count
        }