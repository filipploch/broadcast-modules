"""Sprawdzenia składu meczowego jednej drużyny (W7e-2a): wspólne dla obu modułów."""


def duplicate_number_warnings(rows):
    """Informacja o powtórzonym numerze w JEDNYM składzie meczowym jednej drużyny (zasada właściciela: numery są sprawą organizatora rozgrywek, powtórzenie niczego nie blokuje).

    rows: pary (numer, nazwa zawodnika) z całego składu (w Garbarni: grający i rezerwowi razem).
    Numer pusty się nie liczy. Zwraca listę tekstów, po jednym na powtórzony numer, rosnąco po numerze."""
    by_number = {}
    for number, name in rows:
        if number is None:
            continue
        by_number.setdefault(number, []).append(name)
    return [f"Powtórzony numer {n}: {', '.join(names)}" for n, names in sorted(by_number.items()) if len(names) > 1]


def plays_for_own_team(player, pg):
    """Czy zmiana w składzie meczowym (pg) wolno przepisać na kartę zawodnika (player)?

    Tak tylko wtedy, gdy zawodnik gra dla swojej drużyny. Zawodnik dodany awaryjnie do cudzego składu (pg.team_id != player.team_id)
    ma numer, rolę i opaskę ważne tylko w tym meczu; zmiana nie może ruszać jego karty w drużynie macierzystej."""
    return player is not None and player.team_id == pg.team_id


def squad_warnings(game_players):
    """Ostrzeżenia dla składu meczowego jednej drużyny: lista GamePlayer (w Garbarni grający i rezerwowi razem)."""
    return duplicate_number_warnings((gp.number, f"{gp.player.last_name} {gp.player.first_name}") for gp in game_players)
