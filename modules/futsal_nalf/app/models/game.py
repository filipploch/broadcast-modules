"""Game — moduł futsal-nalf.

Rozszerza BaseGameMixin o pola specyficzne dla futsalu:
  - home_team_fouls, away_team_fouls
  - is_home_team_lost_by_wo, is_away_team_lost_by_wo
  - relacja do Shootout

Nadpisuje calculate_league_table z sortowaniem wg regulaminu NALF
z uwzględnieniem podziału na grupy (faza grupowa Dywizji B).
"""
from core.extensions import db
from core.models.base_game import BaseGameMixin


def sort_group(tied_rows, all_games):
    """
    Sortuje grupę drużyn z równą liczbą punktów wg regulaminu NALF.

    Kryteria (mini-tabela bezpośrednich spotkań między remisującymi):
      a. punkty w mini-tabeli
      b. bilans bramek w mini-tabeli
      c. bilans bramek globalny
      d. bramki zdobyte globalnie
      e. kolejność stabilna (losowanie — poza zasięgiem algorytmu)
    """
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

    home_team_fouls = db.Column(db.Integer, nullable=False, default=0)
    away_team_fouls = db.Column(db.Integer, nullable=False, default=0)

    is_home_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)
    is_away_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)

    shootout = db.relationship('Shootout', backref='game',
                               uselist=False, cascade='all, delete-orphan'
                               )

    # ------------------------------------------------------------------ #
    # Tabela ligowa                                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def calculate_league_table(cls, league_id, group_nr=1, include_pending=False):
        """
        Oblicza tabelę ligową wg regulaminu NALF.

        Priorytet zerowy: league_group_nr z LeagueTeam.
          - group_nr=1 (mistrzowska) wyżej niż group_nr=2 (spadkowa)
          - jeśli wszystkie drużyny mają group_nr=1 — kryterium bez wpływu

        Args:
            league_id:    ID ligi
            group_nr:     numer rundy/grupy rozgrywek w tabeli games
            include_pending: True  -> tabela wirtualna (FINISHED + PENDING)
                          False -> tabela oficjalna (tylko FINISHED)

        Returns:
            lista dict posortowana wg regulaminu NALF
        """
        from core.utils.standings import apply_tiebreakers
        from core.models.base_league_team import get_league_team_model

        stats_list = super().calculate_league_table(
            league_id, group_nr=group_nr, include_pending=include_pending
        )
        if not stats_list:
            return stats_list

        # Dołącz league_group_nr z LeagueTeam do każdego wiersza
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
            # Brak podziału — sortuj globalnie
            return apply_tiebreakers(stats_list, all_finished, sort_group)

        # Podział na grupy — sortuj wewnątrz każdej grupy osobno,
        # sklejaj w kolejności rosnącej league_group_nr (1 wyżej niż 2)
        result = []
        for lg_nr in sorted(unique_groups):
            group_rows = [r for r in stats_list if r['league_group_nr'] == lg_nr]
            result.extend(apply_tiebreakers(group_rows, all_finished, sort_group))
        return result

    @classmethod
    def get_league_tables(cls, league_id, group_nr=1):
        """
        Zwraca obie wersje tabeli ligowej w formacie JSON-ready.

        Returns:
            dict z kluczami:
              'official'  -> tabela tylko z meczów zakończonych
              'virtual'   -> tabela z meczów zakończonych + live
              'has_live'  -> bool, czy trwa jakiś mecz
        """
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

    # ------------------------------------------------------------------ #
    # Serializacja                                                         #
    # ------------------------------------------------------------------ #

    def to_dict(self):
        d = super().to_dict()
        current_period = self.get_current_period()
        d['home_team_fouls']         = current_period.home_team_fouls if current_period else 0
        d['away_team_fouls']         = current_period.away_team_fouls if current_period else 0
        d['is_home_team_lost_by_wo'] = self.is_home_team_lost_by_wo
        d['is_away_team_lost_by_wo'] = self.is_away_team_lost_by_wo
        d['is_walkover']             = self.is_walkover
        d['is_double_walkover']      = self.is_double_walkover
        d['has_shootout']            = self.has_shootout
        d['full_score_string']       = self.full_score_string
        d['shootout']                = self.shootout.to_dict() if self.shootout else None
        return d
