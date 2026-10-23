"""Klient WordPressa/SportsPressa modułu (WP-2): adres z module.json, logowanie hasłem aplikacji, lista rozgrywek.

Jedno źródło parametrów dla obu sposobów startu instancji WP (plik .bat i HUB): blok "wp" w module.json modułu.
Dane logowania leżą poza repozytorium, w <wp_dir>/dane-api-<id modułu>.json: {"user": "...", "password": "..."}.
Bez pliku moduł pyta anonimowo (WP zwraca wtedy tylko opublikowane mecze).

Pozycja listy rozgrywek to para (liga, sezon), która ma w WP przynajmniej jeden mecz oznaczony obiema kategoriami."""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REQUEST_TIMEOUT_S = 6
PER_PAGE = 100


class WpError(Exception):
    """Błąd rozmowy z WP. kind: connection | auth | http | format."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


@dataclass
class WpConfig:
    enabled: bool = False
    module_id: str = ''
    port: int = 0
    title: str = ''
    url: str = ''
    user: str = ''
    password: str = ''
    creds_file: str = ''
    problem: str = ''          # powód, dla którego konfiguracja jest niepełna (komunikat dla operatora)
    extra: dict = field(default_factory=dict)

    @property
    def has_auth(self):
        return bool(self.user and self.password)


def default_wp_dir(module_dir):
    """Folder wp-local obok repozytorium (modules/<moduł> -> katalog główny -> wp-local); BM_WP_DIR (ustawia HUB) ma pierwszeństwo."""
    env = os.environ.get('BM_WP_DIR')
    if env:
        return Path(env)
    return Path(module_dir).resolve().parents[1] / 'wp-local'


def load_wp_config(module_dir, wp_dir=None):
    """Czyta blok "wp" z <module_dir>/module.json i dane logowania. Nigdy nie zgłasza wyjątku: problem trafia do cfg.problem."""
    cfg = WpConfig()
    path = Path(module_dir) / 'module.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as e:
        cfg.problem = f'nie można odczytać {path.name}: {e}'
        return cfg
    cfg.module_id = str(data.get('id') or '')
    block = data.get('wp')
    if not isinstance(block, dict):
        return cfg                                   # moduł bez własnego WP
    port = block.get('port')
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        cfg.problem = f'blok wp w {path.name}: nieprawidłowy port {port!r}'
        return cfg
    cfg.enabled, cfg.port, cfg.title = True, port, str(block.get('title') or '')
    cfg.url = f'http://127.0.0.1:{port}'
    creds = Path(wp_dir) if wp_dir else default_wp_dir(module_dir)
    cfg.creds_file = str(creds / f'dane-api-{cfg.module_id}.json')
    try:
        raw = json.loads(Path(cfg.creds_file).read_text(encoding='utf-8-sig'))
        cfg.user, cfg.password = str(raw.get('user') or ''), str(raw.get('password') or '')
    except FileNotFoundError:
        pass                                         # bez pliku: odczyt anonimowy
    except (OSError, ValueError) as e:
        cfg.problem = f'dane logowania WP ({Path(cfg.creds_file).name}) nieczytelne: {e}'
    return cfg


class WpClient:
    def __init__(self, cfg, timeout=REQUEST_TIMEOUT_S):
        self.cfg = cfg
        self.timeout = timeout

    def _request(self, route, params=None):
        q = urllib.parse.urlencode(params or {}, safe=',')
        url = f'{self.cfg.url}/index.php?rest_route=/{route.lstrip("/")}' + (f'&{q}' if q else '')
        headers = {'Accept': 'application/json'}
        if self.cfg.has_auth:
            token = base64.b64encode(f'{self.cfg.user}:{self.cfg.password}'.encode()).decode()
            headers['Authorization'] = f'Basic {token}'
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body, hdrs = r.read(), r.headers
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise WpError('auth', f'WP odrzucił dane logowania (HTTP {e.code})')
            raise WpError('http', f'WP odpowiedział błędem HTTP {e.code}')
        except (urllib.error.URLError, OSError) as e:
            raise WpError('connection', f'brak połączenia z WP ({self.cfg.url}): {getattr(e, "reason", e)}')
        try:
            return json.loads(body.decode('utf-8')), hdrs
        except ValueError:
            raise WpError('format', 'WP zwrócił odpowiedź, która nie jest JSON-em')

    def get_all(self, route, params=None):
        """Wszystkie strony kolekcji (per_page=100)."""
        out, page = [], 1
        while True:
            data, hdrs = self._request(route, {**(params or {}), 'per_page': PER_PAGE, 'page': page})
            if not isinstance(data, list):
                raise WpError('format', f'oczekiwano listy z {route}')
            out.extend(data)
            try:
                pages = int(hdrs.get('X-WP-TotalPages') or 1)
            except ValueError:
                pages = 1
            if page >= pages:
                return out
            page += 1

    def ping(self):
        self._request('sportspress/v2/leagues', {'per_page': 1, '_fields': 'id'})


def fetch_competitions(client):
    """Lista rozgrywek (par liga + sezon z meczami) i liczba meczów bez ligi lub sezonu."""
    leagues = {int(x['id']): x for x in client.get_all('sportspress/v2/leagues', {'_fields': 'id,name,slug'})}
    seasons = {int(x['id']): x for x in client.get_all('sportspress/v2/seasons', {'_fields': 'id,name,slug'})}
    status = 'publish,future' if client.cfg.has_auth else 'publish'
    events = client.get_all('sportspress/v2/events', {'status': status, '_fields': 'id,date,leagues,seasons'})
    pairs = defaultdict(lambda: {'events': 0, 'dates': []})
    unassigned = 0
    for ev in events:
        ls = [int(i) for i in (ev.get('leagues') or [])]
        ss = [int(i) for i in (ev.get('seasons') or [])]
        if not ls or not ss:
            unassigned += 1
            continue
        for l in ls:
            for s in ss:
                p = pairs[(l, s)]
                p['events'] += 1
                if ev.get('date'):
                    p['dates'].append(str(ev['date'])[:10])
    items = []
    for (l, s), p in pairs.items():
        lg, se = leagues.get(l, {}), seasons.get(s, {})
        items.append({
            'key': f'{l}:{s}', 'league_id': l, 'season_id': s,
            'league_name': lg.get('name') or f'liga {l}', 'league_slug': lg.get('slug') or '',
            'season_name': se.get('name') or f'sezon {s}', 'season_slug': se.get('slug') or '',
            'events': p['events'], 'first_date': min(p['dates']) if p['dates'] else '', 'last_date': max(p['dates']) if p['dates'] else '',
        })
    items.sort(key=lambda i: (i['league_name'].lower(), i['season_name'].lower()))
    return {'items': items, 'unassigned': unassigned, 'total_events': len(events),
            'fetched_at': datetime.now().isoformat(timespec='seconds')}
