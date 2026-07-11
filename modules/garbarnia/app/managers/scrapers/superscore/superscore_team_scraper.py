"""Superscore Team Scraper — wyciąga unikalne drużyny z API superscore.live (lista meczów).

Współdzieli endpoint z SuperscoreGameScraper (fixtures), ale zamiast wyniku
meczu interesuje nas team1/team2: pełna nazwa + seo_id (slug, hash) potrzebne
do zbudowania foreign_id i URL profilu drużyny:
    https://superscore.live/pl-PL/pilka-nozna/druzyny/{slug}/{hash}

foreign_id zapisywany jako 'slug/hash' — ten sam string, który wystarczy
podstawić za {slug}/{hash} żeby dostać działający URL. Sam hash bez slugu nie
odtwarza URL bez dodatkowego zapytania; sam slug nie jest stabilny (zmienia
się przy zmianie nazwy klubu) — stąd oba razem w jednym polu.
"""
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

_API_BASE = (
    'https://scorealarm-stats.freetls.fastly.net'
    '/v2/soccer/fixtures/season/plsuperscore/pl-PL'
)


class SuperscoreTeamScraper:
    """Scraper drużyn z listy meczów (fixtures) superscore.live."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; broadcast-scraper/1.0)',
            'Accept':     'application/json',
        })

    def scrape_teams(self, season_id: str) -> list[dict]:
        """
        Pobierz unikalne drużyny z terminarza sezonu.

        Args:
            season_id: ID sezonu z superscore.live (np. '4vDT5gZAVMkCxWuCYl8kzc')

        Returns:
            Lista słowników {'name': str, 'foreign_id': str, 'short_code': str|None}
            (foreign_id = 'slug/hash', short_code = trzyliterowy skrót z superscore —
            może różnić się od short_name już zapisanego w bazie przez inny scraper)

        Raises:
            RuntimeError: błąd sieciowy albo API zwróciło pustą/niepoprawną
                odpowiedź (np. błędny season_id) — sygnalizowane jawnie zamiast
                cichego zwrócenia pustej listy, żeby nie wyglądało to jak
                "wszystko już dopasowane".
        """
        params = {'season-id': season_id, 'with-upcoming': 'yes'}
        try:
            resp = self.session.get(_API_BASE, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Błąd pobierania drużyn z superscore API: {e}")
            raise RuntimeError(f"Błąd pobierania danych z superscore API: {e}") from e

        if not resp.content:
            logger.error(f"Superscore API zwróciło pustą odpowiedź (status {resp.status_code}) dla season_id={season_id!r}")
            raise RuntimeError(
                f"Superscore API zwróciło pustą odpowiedź (status {resp.status_code}) — "
                f"sprawdź, czy Superscore Season ID '{season_id}' jest poprawny."
            )

        try:
            data = resp.json()
        except ValueError as e:
            logger.error(f"Superscore API zwróciło dane w nieoczekiwanym formacie: {e}")
            raise RuntimeError(f"Superscore API zwróciło dane w nieoczekiwanym formacie: {e}") from e

        events = data.get('events') or []
        teams_by_foreign_id = {}
        for event in events:
            for key in ('team1', 'team2'):
                parsed = self._extract_team(event.get(key) or {})
                if parsed:
                    teams_by_foreign_id[parsed['foreign_id']] = parsed

        teams = list(teams_by_foreign_id.values())
        logger.info(f"Sparsowano {len(teams)} unikalnych drużyn z {len(events)} eventów")
        return teams

    @staticmethod
    def _extract_team(team: dict) -> Optional[dict]:
        name = team.get('name')
        if not name:
            for entry in team.get('names') or []:
                if entry.get('type') == 1:
                    val = entry.get('value') or {}
                    name = val.get('string_value') or val.get('stringValue')
                    if name:
                        break
        if not name or not name.strip():
            return None

        seo_id = team.get('seo_id') or {}
        slug = (seo_id.get('slug') or {}).get('value')
        team_hash = (seo_id.get('hash') or {}).get('value')
        if not slug or not team_hash:
            return None

        short_code = (team.get('short_code') or {}).get('value')
        short_code = short_code.strip()[:3].upper() if short_code else None

        return {
            'name': name.strip(),
            'foreign_id': f'{slug}/{team_hash}',
            'short_code': short_code,
        }
