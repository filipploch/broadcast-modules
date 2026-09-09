"""Deskryptory UI scraperów — moduł futsal-nalf.

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

futsal-nalf ma jeden scraper ('nalffutsal'). Lista drużyn nie jest scrapowana
(patrz app/managers/team_scraper_manager.py), a kadra pobierana jest osobnym
przyciskiem "Pobierz zawodników" (nie kaskadą) — stąd puste teams/players.
"""
from app.models.scraper import Scraper


def _sid(folder):
    scraper = Scraper.get_by_folder(folder)
    return scraper.id if scraper else None


def _nalffutsal_games_ready(league):
    sid = _sid('nalffutsal')
    return bool(sid and league.get_scraper_url(sid, 'games_url'))


SCRAPER_UI = {
    'games': [
        {
            'id': 'nalffutsal',
            'label': 'NALF Futsal',
            'trigger_view': 'scrape_games',
            'status_url': '/api/games/scrape/status',
            'checked': True,
            'ready': _nalffutsal_games_ready,
        },
    ],
    'teams': [],
    'players': [],
}
