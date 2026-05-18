"""Game — moduł turniej.

Rozszerza BaseGameMixin o foule drużynowe.
Bez systemu shootout i pól walkover.
"""
from core.extensions import db
from core.models.base_game import BaseGameMixin


def sort_group(tied_rows, all_games):
    from core.utils.standings import compute_mini_table

    if len(tied_rows) == 1:
        return tied_rows

    ids = [r['team_id'] for r in tied_rows]
    mini = compute_mini_table(ids, all_games)

    return sorted(tied_rows, key=lambda r: (
        mini[r['team_id']]['points'],
        mini[r['team_id']]['gd'],
        r['goal_difference'],
        r['goals_scored'],
    ), reverse=True)


class Game(BaseGameMixin, db.Model):
    __tablename__ = 'games'

    foreign_id      = None
    home_team_fouls = db.Column(db.Integer, nullable=False, default=0)
    away_team_fouls = db.Column(db.Integer, nullable=False, default=0)

    shootout = db.relationship('Shootout', uselist=False, backref='game',
                               cascade='all, delete-orphan',
                               foreign_keys='Shootout.game_id')

    @property
    def is_home_team_lost_by_wo(self):
        return False

    @is_home_team_lost_by_wo.setter
    def is_home_team_lost_by_wo(self, value):
        pass

    @property
    def is_away_team_lost_by_wo(self):
        return False

    @is_away_team_lost_by_wo.setter
    def is_away_team_lost_by_wo(self, value):
        pass

    @classmethod
    def calculate_league_table(cls, league_id, group_nr=1, include_pending=False):
        from core.utils.standings import apply_tiebreakers
        from core.models.base_league_team import get_league_team_model

        stats_list = super().calculate_league_table(
            league_id, group_nr=group_nr, include_pending=include_pending
        )
        if not stats_list:
            return stats_list

        LeagueTeam = get_league_team_model()
        team_group = {
            lt.team_id: lt.group_nr
            for lt in LeagueTeam.query.filter_by(league_id=league_id).all()
        }
        for row in stats_list:
            row['league_group_nr'] = team_group.get(row['team_id'], 1)

        all_finished = cls.query.filter_by(
            league_id=league_id,
            group_nr=group_nr,
            status=cls.STATUS_FINISHED,
        ).all()

        unique_groups = set(row['league_group_nr'] for row in stats_list)

        if len(unique_groups) == 1:
            return apply_tiebreakers(stats_list, all_finished, sort_group)

        result = []
        for lg_nr in sorted(unique_groups):
            group_rows = [r for r in stats_list if r['league_group_nr'] == lg_nr]
            result.extend(apply_tiebreakers(group_rows, all_finished, sort_group))
        return result

    @classmethod
    def get_league_tables(cls, league_id, group_nr=1):
        official = cls.calculate_league_table(
            league_id, group_nr=group_nr, include_pending=False
        )
        virtual = cls.calculate_league_table(
            league_id, group_nr=group_nr, include_pending=True
        )
        has_live = cls.query.filter_by(
            league_id=league_id,
            group_nr=group_nr,
            status=cls.STATUS_PENDING,
        ).count() > 0

        return {
            'official': official,
            'virtual': virtual,
            'has_live': has_live,
        }

    def to_dict(self):
        d = super().to_dict()
        d['home_team_fouls'] = self.home_team_fouls
        d['away_team_fouls'] = self.away_team_fouls
        return d
