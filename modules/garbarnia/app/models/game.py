"""Game — moduł garbarnia.

Rozszerza BaseGameMixin o pola specyficzne dla piłki nożnej:
  - home_team_fouls, away_team_fouls
  - is_home_team_lost_by_wo, is_away_team_lost_by_wo
  - relacja do Shootout

Nadpisuje calculate_league_table z sortowaniem wg regulaminu MZPN IV Liga.
"""
from core.extensions import db
from core.models.base_game import BaseGameMixin


def sort_group(tied_rows, all_games):
    """
    Sortuje grupę drużyn z równą liczbą punktów wg regulaminu MZPN IV Liga.

    Kryteria (mini-tabela bezpośrednich spotkań między remisującymi):
      1. punkty w mini-tabeli
      2. bilans bramek w mini-tabeli
      3. bilans bramek globalny
      4. bramki zdobyte globalnie
      5. zwycięstwa globalnie
      6. zwycięstwa wyjazdowe globalnie
      7. kolejność stabilna (losowanie — poza zasięgiem algorytmu)

    Przy >2 drużynach stosuje się zasady rekurencyjnie między wciąż
    remisującymi po kryterium 1-2 mini-tabeli.
    """
    from core.utils.standings import compute_mini_table, count_away_wins

    if len(tied_rows) == 1:
        return tied_rows

    ids = [r['team_id'] for r in tied_rows]
    mini = compute_mini_table(ids, all_games)

    sorted_rows = sorted(tied_rows, key=lambda r: (
        mini[r['team_id']]['points'],
        mini[r['team_id']]['gd'],
        r['goal_difference'],
        r['goals_scored'],
        r['wins'],
        count_away_wins(r['team_id'], all_games),
    ), reverse=True)

    # Rekurencja: podgrupy nadal remisujące po kryteriach 1-2 mini-tabeli
    # sortujemy po kryteriach 3-6 (globalne)
    result = []
    i = 0
    while i < len(sorted_rows):
        j = i + 1
        while j < len(sorted_rows):
            ti = sorted_rows[i]['team_id']
            tj = sorted_rows[j]['team_id']
            if (mini[ti]['points'] == mini[tj]['points']
                    and mini[ti]['gd'] == mini[tj]['gd']):
                j += 1
            else:
                break
        if j - i > 1:
            sub = sorted(sorted_rows[i:j], key=lambda r: (
                r['goal_difference'],
                r['goals_scored'],
                r['wins'],
                count_away_wins(r['team_id'], all_games),
            ), reverse=True)
            result.extend(sub)
        else:
            result.append(sorted_rows[i])
        i = j

    return result


class Game(BaseGameMixin, db.Model):
    __tablename__ = 'games'

    home_team_red_cards = db.Column(db.Integer, nullable=False, default=0)
    away_team_red_cards = db.Column(db.Integer, nullable=False, default=0)

    is_home_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)
    is_away_team_lost_by_wo = db.Column(db.Boolean, nullable=False, default=False)

    shootout = db.relationship('Shootout', backref='game',
                               uselist=False, cascade='all, delete-orphan')

    # ------------------------------------------------------------------ #
    # Tabela ligowa                                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def calculate_league_table(cls, league_id, group_nr=1, include_pending=False):
        """
        Oblicza tabelę ligową wg regulaminu MZPN IV Liga.

        Args:
            league_id:    ID ligi
            group_nr:     numer grupy (zawsze 1 w garbarni)
            include_pending: True  -> tabela wirtualna (FINISHED + PENDING)
                          False -> tabela oficjalna (tylko FINISHED)

        Returns:
            lista dict posortowana wg regulaminu MZPN
        """
        from core.utils.standings import apply_tiebreakers

        stats_list = super().calculate_league_table(
            league_id, group_nr=group_nr, include_pending=include_pending
        )

        all_finished = cls.query.filter_by(
            league_id=league_id,
            group_nr=group_nr,
            status=cls.STATUS_FINISHED,
        ).all()

        return apply_tiebreakers(stats_list, all_finished, sort_group)

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
        d['home_team_red_cards']     = self.home_team_red_cards
        d['away_team_red_cards']     = self.away_team_red_cards
        d['is_home_team_lost_by_wo'] = self.is_home_team_lost_by_wo
        d['is_away_team_lost_by_wo'] = self.is_away_team_lost_by_wo
        d['is_walkover']             = self.is_walkover
        d['is_double_walkover']      = self.is_double_walkover
        d['has_shootout']            = self.has_shootout
        d['full_score_string']       = self.full_score_string
        d['shootout']                = self.shootout.to_dict() if self.shootout else None
        d['home_team_coach']         = self.home_team.coach if self.home_team else None
        d['away_team_coach']         = self.away_team.coach if self.away_team else None
        return d
