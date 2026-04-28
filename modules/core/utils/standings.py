"""
core/utils/standings.py

Generyczne narzędzia do obliczania tabeli ligowej.
Funkcje sort_group() są definiowane w modułach (garbarnia/futsal_nalf).
"""


def compute_mini_table(tied_team_ids, all_games):
    """
    Oblicza mini-tabelę bezpośrednich spotkań między podanymi drużynami.

    Args:
        tied_team_ids: zbiór/lista team_id drużyn remisujących punktami
        all_games:     lista obiektów Game (zakończonych) z całych rozgrywek

    Returns:
        dict: team_id -> {'points': int, 'gf': int, 'ga': int, 'gd': int}
    """
    ids = set(tied_team_ids)
    mini = {tid: {'points': 0, 'gf': 0, 'ga': 0, 'gd': 0} for tid in ids}

    for game in all_games:
        h, a = game.home_team_id, game.away_team_id
        if h not in ids or a not in ids:
            continue
        if not game.is_finished:
            continue
        hs = game.get_home_team_stats()
        as_ = game.get_away_team_stats()
        if hs:
            mini[h]['points'] += hs['points']
            mini[h]['gf']     += hs['goals_scored']
            mini[h]['ga']     += hs['goals_lost']
        if as_:
            mini[a]['points'] += as_['points']
            mini[a]['gf']     += as_['goals_scored']
            mini[a]['ga']     += as_['goals_lost']

    for s in mini.values():
        s['gd'] = s['gf'] - s['ga']

    return mini


def count_away_wins(team_id, all_games):
    """Liczy zwycięstwa wyjazdowe drużyny w podanych meczach."""
    count = 0
    for game in all_games:
        if game.away_team_id == team_id and game.is_finished:
            s = game.get_away_team_stats()
            if s and s['wins'] == 1:
                count += 1
    return count


def apply_tiebreakers(stats_list, all_games, sort_group_fn):
    """
    Główna funkcja sortowania tabeli z obsługą tie-breakerów.

    Algorytm:
      1. Sortuj wstępnie po punktach (DESC)
      2. Dla każdej grupy drużyn z równą liczbą punktów wywołaj sort_group_fn
      3. Sklejaj wyniki

    Args:
        stats_list:    lista dict ze statystykami drużyn
        all_games:     lista wszystkich Game z rozgrywek (do mini-tabeli)
        sort_group_fn: funkcja(tied_rows, all_games) -> sorted list
                       zdefiniowana w module (garbarnia lub futsal_nalf)

    Returns:
        posortowana lista dict
    """
    by_points = sorted(stats_list, key=lambda x: x['points'], reverse=True)

    result = []
    i = 0
    while i < len(by_points):
        j = i + 1
        while j < len(by_points) and by_points[j]['points'] == by_points[i]['points']:
            j += 1
        group = by_points[i:j]
        result.extend(sort_group_fn(group, all_games) if len(group) > 1 else group)
        i = j

    return result
