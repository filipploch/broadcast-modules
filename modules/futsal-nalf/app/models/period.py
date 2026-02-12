"""Period model - Game periods (halves, quarters, etc.)"""
from app.extensions import db
from datetime import datetime


class Period(db.Model):
    """Period within a game (e.g., 1st half, 2nd half)"""
    __tablename__ = 'periods'

    # Status constants (same as Game model)
    STATUS_NOT_STARTED = 0
    STATUS_PENDING = 1  # Live/In Progress
    STATUS_FINISHED = 2

    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False, index=True)
    
    # Period configuration
    period_order = db.Column(db.Integer, nullable=False)  # 1, 2, 3, etc.
    description = db.Column(db.String(100), nullable=False)  # "1. połowa", "2. połowa", etc.
    main_timer_name = db.Column(db.String(200), nullable=True)  # Timer name for this period
    
    # Scores for this period
    home_team_goals = db.Column(db.Integer, default=0, nullable=False)
    away_team_goals = db.Column(db.Integer, default=0, nullable=False)
    home_team_fouls = db.Column(db.Integer, default=0, nullable=False)
    away_team_fouls = db.Column(db.Integer, default=0, nullable=False)
    
    # Time settings (in milliseconds)
    initial_time = db.Column(db.Integer, default=0, nullable=False)  # Starting time for stopwatch
    limit_time = db.Column(db.Integer, default=1200000, nullable=False)  # 20 minutes = 1200000 ms
    pause_at_limit = db.Column(db.Boolean, default=True, nullable=False)
    
    # Status
    status = db.Column(db.Integer, default=STATUS_NOT_STARTED, nullable=False, index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: period_order must be unique per game
    __table_args__ = (
        db.UniqueConstraint('game_id', 'period_order', name='unique_game_period_order'),
    )

    def __repr__(self):
        return f'<Period {self.period_order} for game_id={self.game_id}: {self.description}>'
    
    def generate_timer_name(self):
        """
        Generate timer name based on game teams and period order
        Format: '{home_team_short}x{away_team_short} p:{period_order}'
        Example: 'TORxLEG p:1'
        """
        if not self.game:
            return None
        
        home_short = self.game.home_team.short_name if self.game.home_team else '???'
        away_short = self.game.away_team.short_name if self.game.away_team else '???'
        
        return f'{home_short}x{away_short} p:{self.period_order}'
    
    def update_timer_name(self):
        """Update main_timer_name based on current game state"""
        self.main_timer_name = self.generate_timer_name()
        self.updated_at = datetime.utcnow()

    def get_status_text(self):
        """Get human-readable status text"""
        status_map = {
            self.STATUS_NOT_STARTED: 'Nie rozpoczęto',
            self.STATUS_PENDING: 'Trwa',
            self.STATUS_FINISHED: 'Zakończono'
        }
        return status_map.get(self.status, 'Nieznany')

    @property
    def limit_time_seconds(self):
        """Get limit time in seconds"""
        return self.limit_time / 1000 if self.limit_time else 0

    @property
    def initial_time_seconds(self):
        """Get initial time in seconds"""
        return self.initial_time / 1000 if self.initial_time else 0

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'game_id': self.game_id,
            'period_order': self.period_order,
            'description': self.description,
            'main_timer_name': self.main_timer_name,
            'home_team_goals': self.home_team_goals,
            'away_team_goals': self.away_team_goals,
            'home_team_fouls': self.home_team_fouls,
            'away_team_fouls': self.away_team_fouls,
            'initial_time': self.initial_time,
            'initial_time_seconds': self.initial_time_seconds,
            'limit_time': self.limit_time,
            'limit_time_seconds': self.limit_time_seconds,
            'pause_at_limit': self.pause_at_limit,
            'status': self.status,
            'status_text': self.get_status_text(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @staticmethod
    def calculate_initial_time_for_period(game_id, period_order):
        """
        Calculate initial_time for a period based on sum of limit_time of previous periods
        
        Args:
            game_id: Game ID
            period_order: Period order number (1, 2, 3, etc.)
        
        Returns:
            Initial time in milliseconds (sum of previous periods' limit_time)
        """
        if period_order == 1:
            return 0
        
        # Sum limit_time of all previous periods for this game
        previous_periods = Period.query.filter(
            Period.game_id == game_id,
            Period.period_order < period_order
        ).all()
        
        total_time = sum(p.limit_time for p in previous_periods)
        return total_time

    def update_score(self, home_goals, away_goals):
        """Update period score"""
        self.home_team_goals = home_goals
        self.away_team_goals = away_goals
        self.updated_at = datetime.utcnow()

    def update_fouls(self, home_fouls, away_fouls):
        """Update period fouls"""
        self.home_team_fouls = home_fouls
        self.away_team_fouls = away_fouls
        self.updated_at = datetime.utcnow()

    def increment_home_goals(self):
        """Increment home team goals in this period"""
        self.home_team_goals += 1
        self.updated_at = datetime.utcnow()

    def increment_away_goals(self):
        """Increment away team goals in this period"""
        self.away_team_goals += 1
        self.updated_at = datetime.utcnow()

    def increment_home_fouls(self):
        """Increment home team fouls in this period"""
        self.home_team_fouls += 1
        self.updated_at = datetime.utcnow()

    def increment_away_fouls(self):
        """Increment away team fouls in this period"""
        self.away_team_fouls += 1
        self.updated_at = datetime.utcnow()

    def sync_to_game(self):
        """
        Synchronize this period's scores to the parent game
        
        Updates Game:
        - home_team_goals = sum of all periods' home_team_goals
        - away_team_goals = sum of all periods' away_team_goals
        - home_team_fouls = current period's home_team_fouls
        - away_team_fouls = current period's away_team_fouls
        """
        from app.extensions import db
        
        game = self.game
        if not game:
            return
        
        # Sum goals from all periods
        all_periods = Period.query.filter_by(game_id=self.game_id).all()
        total_home_goals = sum(p.home_team_goals for p in all_periods)
        total_away_goals = sum(p.away_team_goals for p in all_periods)
        
        # Update game goals (sum of all periods)
        game.home_team_goals = total_home_goals
        game.away_team_goals = total_away_goals
        
        # Update game fouls (from current/active period only)
        current_period = game.get_current_period()
        if current_period:
            game.home_team_fouls = current_period.home_team_fouls
            game.away_team_fouls = current_period.away_team_fouls
        else:
            # If no active period, use this period (might be during finish)
            game.home_team_fouls = self.home_team_fouls
            game.away_team_fouls = self.away_team_fouls
        
        game.updated_at = datetime.utcnow()
        db.session.commit()

    @staticmethod
    def sync_all_periods_to_game(game_id):
        """
        Synchronize all periods to game
        
        This recalculates Game scores based on all Period data:
        - Goals = sum of all periods
        - Fouls = current active period (or last period if none active)
        
        Args:
            game_id: Game ID
        """
        from app.extensions import db
        from app.models.game import Game
        
        game = Game.query.get(game_id)
        if not game:
            return
        
        periods = Period.query.filter_by(game_id=game_id).order_by(Period.period_order).all()
        
        if not periods:
            return
        
        # Sum goals from all periods
        total_home_goals = sum(p.home_team_goals for p in periods)
        total_away_goals = sum(p.away_team_goals for p in periods)
        
        game.home_team_goals = total_home_goals
        game.away_team_goals = total_away_goals
        
        # Fouls from current/active period
        current_period = game.get_current_period()
        if current_period:
            game.home_team_fouls = current_period.home_team_fouls
            game.away_team_fouls = current_period.away_team_fouls
        else:
            # No active period - use last period
            last_period = periods[-1] if periods else None
            if last_period:
                game.home_team_fouls = last_period.home_team_fouls
                game.away_team_fouls = last_period.away_team_fouls
        
        game.updated_at = datetime.utcnow()
        db.session.commit()