"""Superscore Player Scraper — wyciąga kadrę drużyny (zawodnicy + trener) z API
superscore.live.

API endpoint:
    https://scorealarm-stats.freetls.fastly.net/v2/soccer/teams/squad/plsuperscore/pl-PL
    ?team-id={hash}

{hash} to ten sam hash co w foreign_id drużyny ('slug/hash', patrz
superscore_team_scraper.py) — bez slugu.

Odpowiedź grupuje zawodników w tablicach goalkeepers/defenders/midfielders/
attackers/other — kategoria goalkeepers mapowana jest na is_goalkeeper=True,
reszta (w praktyce dla niższych lig prawie wszyscy trafiają do "other" bez
przypisanej pozycji) na False. Trener jest pod kluczem "manager".name
(pełne imię i nazwisko w kolejności Imię Nazwisko — inaczej niż u zawodników,
gdzie player.name to "Nazwisko, Imię").
"""
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

_API_BASE = (
    'https://scorealarm-stats.freetls.fastly.net'
    '/v2/soccer/teams/squad/plsuperscore/pl-PL'
)

_POSITION_KEYS = ('goalkeepers', 'defenders', 'midfielders', 'attackers', 'other')


class SuperscorePlayerScraper:
    """Scraper kadry drużyny (skład) z superscore.live."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; broadcast-scraper/1.0)',
            'Accept':     'application/json',
        })

    def scrape_squad(self, team_hash: str) -> dict:
        """
        Pobierz kadrę drużyny.

        Args:
            team_hash: hash drużyny z superscore.live (część foreign_id po '/')

        Returns:
            {'manager_name': str|None, 'players': [{'first_name', 'last_name',
             'foreign_id', 'is_goalkeeper'}]}

        Raises:
            RuntimeError: błąd sieciowy albo API zwróciło pustą/niepoprawną
                odpowiedź (np. błędny team_hash) — sygnalizowane jawnie zamiast
                cichego zwrócenia pustej listy.
        """
        params = {'team-id': team_hash}
        try:
            resp = self.session.get(_API_BASE, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Błąd pobierania kadry z superscore API: {e}")
            raise RuntimeError(f"Błąd pobierania danych z superscore API: {e}") from e

        if not resp.content:
            logger.error(f"Superscore API zwróciło pustą odpowiedź (status {resp.status_code}) dla team_hash={team_hash!r}")
            raise RuntimeError(
                f"Superscore API zwróciło pustą odpowiedź (status {resp.status_code}) — "
                f"sprawdź, czy team-id '{team_hash}' jest poprawny."
            )

        try:
            data = resp.json()
        except ValueError as e:
            logger.error(f"Superscore API zwróciło dane w nieoczekiwanym formacie: {e}")
            raise RuntimeError(f"Superscore API zwróciło dane w nieoczekiwanym formacie: {e}") from e

        players = []
        seen_foreign_ids = set()
        for key in _POSITION_KEYS:
            is_goalkeeper = (key == 'goalkeepers')
            for entry in data.get(key) or []:
                parsed = self._extract_player(entry, is_goalkeeper)
                if parsed and parsed['foreign_id'] not in seen_foreign_ids:
                    seen_foreign_ids.add(parsed['foreign_id'])
                    players.append(parsed)

        manager_name = self._extract_manager_name(data.get('manager') or {})

        logger.info(f"Sparsowano {len(players)} zawodników i trenera={manager_name!r} dla team_hash={team_hash}")
        return {'manager_name': manager_name, 'players': players}

    @staticmethod
    def _extract_player(entry: dict, is_goalkeeper: bool) -> Optional[dict]:
        player = entry.get('player') or {}
        seo_id = player.get('seo_id') or {}
        slug = (seo_id.get('slug') or {}).get('value')
        player_hash = (seo_id.get('hash') or {}).get('value')
        if not slug or not player_hash:
            return None

        raw_name = (player.get('name') or '').strip()
        if not raw_name:
            return None

        if ',' in raw_name:
            last_name, first_name = (part.strip() for part in raw_name.split(',', 1))
        else:
            # fallback: brak przecinka — traktuj cały string jako nazwisko
            last_name, first_name = raw_name, ''

        if not last_name or not first_name:
            return None

        return {
            'first_name':    first_name,
            'last_name':     last_name,
            'foreign_id':    f'{slug}/{player_hash}',
            'is_goalkeeper': is_goalkeeper,
        }

    @staticmethod
    def _extract_manager_name(manager: dict) -> Optional[str]:
        name = (manager.get('name') or '').strip()
        if name:
            return name
        for entry in manager.get('names') or []:
            if entry.get('type') == 1:
                val = entry.get('value') or {}
                name = (val.get('string_value') or val.get('stringValue') or '').strip()
                if name:
                    return name
        return None
