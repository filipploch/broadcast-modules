"""Deskryptory UI scraperów — moduł garbarnia.

Każdy wpis opisuje jeden scraper w kaskadzie ("split button" 🔍 Scrapuj X + rozwijana
lista scraperów, patrz static/js/ui/scraper-cascade.js oraz
templates/partials/scraper_cascade.html):

  id           — wartość checkboxa (klucz scrapera)
  label        — etykieta w rozwijanej liście
  trigger_view — nazwa view_function uruchamiającej scraper (url_for)
  status_url   — endpoint pollowania statusu dla zadań async; None => wywołanie
                 synchroniczne (fetchJson)
  checked      — domyślny stan checkboxa
  ready(subj)  — czy scraper jest gotowy dla danej ligi (games/teams) / drużyny
                 (players); subj to obiekt League albo Team

Wspólny builder kontekstu: core/routes/routes_crud.py::_build_cascade.
Wpięcie: app/__init__.py → routes_crud.register_routes(app, ..., scraper_ui=SCRAPER_UI).

Zawartość odpowiada 1:1 wcześniejszej logice zaszytej w routes_crud.py
(has_malopolskizpn_* / has_superscore_* / has_laczynaspilka_*) oraz w szablonach.
"""
from app.models.scraper import Scraper


def _sid(folder):
    scraper = Scraper.get_by_folder(folder)
    return scraper.id if scraper else None


def _mzpn_games_url_ready(league):
    """MZPN (mecze i lista drużyn) wymaga skonfigurowanego URL terminarza ligi."""
    sid = _sid('malopolskizpn')
    return bool(sid and league.get_scraper_url(sid, 'games_url'))


def _superscore_games_ready(league):
    return bool(getattr(league, 'superscore_season_id', None))


def _team_has_foreign_id(folder):
    def _ready(team):
        sid = _sid(folder)
        return bool(sid and team.get_foreign_id(sid))
    return _ready


SCRAPER_UI = {
    'games': [
        {
            'id': 'malopolskizpn',
            'label': 'Małopolski ZPN',
            'trigger_view': 'scrape_games',
            'status_url': '/api/games/scrape/status',
            'checked': True,
            'ready': _mzpn_games_url_ready,
        },
        {
            'id': 'superscore',
            'label': 'Superscore',
            'trigger_view': 'scrape_games_superscore',
            'status_url': '/api/games/scrape/status',
            'checked': True,
            'ready': _superscore_games_ready,
        },
    ],
    'teams': [
        {
            'id': 'superscore',
            'label': 'Superscore',
            'trigger_view': 'scrape_league_teams_superscore',
            'status_url': None,
            'checked': True,
            # odpowiednik dawnego "league.superscore_season_id is defined" w szablonie
            'ready': lambda league: hasattr(league, 'superscore_season_id'),
        },
        {
            'id': 'malopolskizpn',
            'label': 'Małopolski ZPN',
            'trigger_view': 'scrape_league_teams_malopolskizpn',
            'status_url': None,
            'checked': True,
            'ready': _mzpn_games_url_ready,
        },
        {
            'id': 'laczynaspilka',
            'label': 'Łączy Nas Piłka',
            'trigger_view': 'scrape_league_teams_laczynaspilka',
            'status_url': None,
            'checked': True,
            'ready': lambda league: True,
        },
    ],
    'players': [
        {
            'id': 'laczynaspilka',
            'label': 'Łączy Nas Piłka',
            'trigger_view': 'scrape_team_players_laczynaspilka',
            'status_url': None,
            'checked': True,
            'ready': _team_has_foreign_id('laczynaspilka'),
        },
        {
            'id': 'superscore',
            'label': 'Superscore',
            'trigger_view': 'scrape_team_players_superscore',
            'status_url': None,
            'checked': False,
            'ready': _team_has_foreign_id('superscore'),
        },
    ],
}
