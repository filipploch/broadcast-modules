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


def is_outside_squad(pg):
    """Zawodnik w składzie meczowym, którego karta jest w innej drużynie albo bez drużyny (dodany awaryjnie, W7e-2b)."""
    return pg.player is not None and pg.player.team_id != pg.team_id


def team_club_key(team):
    """Klucz klubu drużyny. Do W7e-2c (kolumna club_key) modułowe bazy go nie mają i funkcja zwraca None (klub nieznany)."""
    return getattr(team, 'club_key', None) if team is not None else None


def outside_players(game, team_id, query='', only_free=False, limit=300):
    """Lista zawodników z bazy modułu do awaryjnego dodania do składu drużyny team_id w meczu game (W7e-2b).

    Bez zawodników już będących w składzie tej drużyny. Kolejność: pula klubu drużyny składu (po W7e-2c; do tego czasu własna drużyna),
    potem zawodnicy bez drużyny, potem reszta; wewnątrz alfabetycznie (nazwisko, imię).
    only_free: tylko zawodnicy bez drużyny.
    Pola: tag - '' (własny klub / bez drużyny), 'inny klub' (klub znany i różny) albo 'inna drużyna' (klub nieznany, drużyna inna);
    w_drugiej_druzynie - zawodnik jest już w składzie drugiej drużyny tego meczu (do potwierdzenia, bez blokady).
    Numery nie są sprawdzane: powtórzony numer niczego nie blokuje."""
    from core.models.base_game_player import get_game_player_model
    from core.models.base_player import get_player_model
    from core.models.base_team import get_team_model
    Player, GamePlayer, Team = get_player_model(), get_game_player_model(), get_team_model()
    rows = GamePlayer.query.filter_by(game_id=game.id).all()
    in_this = {r.player_id for r in rows if r.team_id == team_id}
    in_other = {r.player_id for r in rows if r.team_id != team_id}
    teams = {t.id: t for t in Team.query.all()}
    own_club = team_club_key(teams.get(team_id))
    q = (query or '').strip().casefold()

    def same_club(pl):
        if pl.team_id == team_id:
            return True
        ck = team_club_key(teams.get(pl.team_id))
        return own_club is not None and ck is not None and ck == own_club

    out = []
    for pl in Player.query.all():
        if pl.id in in_this or (only_free and pl.team_id is not None):
            continue
        team = teams.get(pl.team_id)
        if q and q not in f'{pl.last_name} {pl.first_name}'.casefold() and q not in (team.name.casefold() if team else ''):
            continue
        if pl.team_id is None:
            group, tag = 1, ''
        elif same_club(pl):
            group, tag = 0, ''
        else:
            group, tag = 2, ('inny klub' if own_club is not None and team_club_key(team) is not None else 'inna drużyna')
        out.append({
            'player_id': pl.id,
            'label': f'{pl.last_name} {pl.first_name}',
            'last_name': pl.last_name, 'first_name': pl.first_name,
            'number': pl.number,
            'team_name': team.name if team else None,
            'tag': tag,
            'w_drugiej_druzynie': pl.id in in_other,
            '_g': group,
        })
    out.sort(key=lambda r: (r['_g'], r['last_name'].casefold(), r['first_name'].casefold()))
    for r in out:
        del r['_g']
    return out[:limit]


MOVE_BLOCKED_MESSAGE = "Zawodnik ma w tym meczu zdarzenia, nie można go przenieść do drugiego składu"


def players_blocking_move(game_id, team_id, player_ids):
    """Zawodnicy z listy, którzy są w składzie drugiej drużyny meczu i mają w tym meczu zdarzenia (bramki, kartki, faule itd.), zmiany albo kary:
    nie wolno ich przenieść do składu team_id (historia meczu wskazywałaby na zawodnika, którego nie ma w składzie). Zwraca ich identyfikatory."""
    from core.models.base_game_event import get_game_event_model
    from core.models.base_game_player import get_game_player_model
    from core.models.base_game_timer import get_game_timer_model
    GamePlayer, GameEvent, GameTimer = get_game_player_model(), get_game_event_model(), get_game_timer_model()
    if not player_ids:
        return []
    kandydaci = {r.player_id for r in GamePlayer.query.filter(
        GamePlayer.game_id == game_id, GamePlayer.team_id != team_id, GamePlayer.player_id.in_(list(player_ids))).all()}
    zablokowani = set()
    for pid in kandydaci:
        if (GameEvent.query.filter_by(game_id=game_id, player_id=pid).first() is not None
                or GameTimer.query.filter_by(game_id=game_id, player_id=pid).first() is not None):
            zablokowani.add(pid)
    try:
        from app.models.substitution import Substitution        # tylko moduły ze zmianami jako osobną tabelą (Garbarnia)
    except ImportError:
        Substitution = None
    if Substitution is not None:
        for pid in kandydaci - zablokowani:
            if (Substitution.query.filter_by(game_id=game_id, player_in_id=pid).first() is not None
                    or Substitution.query.filter_by(game_id=game_id, player_out_id=pid).first() is not None):
                zablokowani.add(pid)
    return sorted(zablokowani)


def move_from_other_squad(game_id, team_id, player_ids):
    """Zawodnik może być w meczu tylko w jednym składzie (unikalna para zawodnik+mecz): dodanie do składu team_id zawodnika, który jest
    w składzie drugiej drużyny tego meczu, przenosi go (po potwierdzeniu w interfejsie). Zwraca liczbę przeniesionych; commit robi wywołujący."""
    from core.extensions import db
    from core.models.base_game_player import get_game_player_model
    GamePlayer = get_game_player_model()
    if not player_ids:
        return 0
    rows = GamePlayer.query.filter(GamePlayer.game_id == game_id, GamePlayer.team_id != team_id, GamePlayer.player_id.in_(list(player_ids))).all()
    for r in rows:
        db.session.delete(r)
    return len(rows)
