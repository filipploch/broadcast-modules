"""Klient REST instancji WordPressa/SportsPressa dla importerów (hasło aplikacji z wp-local/dane-api-<id>.json). Tylko biblioteka standardowa."""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PER_PAGE = 100


class WpRestError(Exception):
    def __init__(self, status, message):
        super().__init__(f'HTTP {status}: {message}')
        self.status = status


def wczytaj_dane_logowania(wp_dir, modul_id):
    plik = Path(wp_dir) / f'dane-api-{modul_id}.json'
    try:
        d = json.loads(plik.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        raise SystemExit(f'Brak pliku z danymi logowania do WP: {plik} (format: {{"user": "...", "password": "..."}}).')
    return d['user'], d['password']


class WpRest:
    def __init__(self, url, user, password, timeout=60):
        self.url = url.rstrip('/')
        self.timeout = timeout
        self._auth = 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()
        self.zapytania = 0

    def zadanie(self, metoda, trasa, body=None, params=None):
        q = urllib.parse.urlencode(params or {}, safe=',')
        url = f'{self.url}/index.php?rest_route=/{trasa.lstrip("/")}' + (f'&{q}' if q else '')
        data = None if body is None else json.dumps(body).encode('utf-8')
        req = urllib.request.Request(url, data=data, method=metoda, headers={
            'Authorization': self._auth, 'Accept': 'application/json', **({'Content-Type': 'application/json'} if data is not None else {})})
        self.zapytania += 1
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode('utf-8') or 'null'), r.headers
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode('utf-8')).get('message', '')
            except Exception:
                msg = ''
            finally:
                e.close()
            raise WpRestError(e.code, msg or e.reason)
        except (urllib.error.URLError, OSError) as e:
            raise WpRestError(0, f'brak połączenia z WP ({self.url}): {getattr(e, "reason", e)}')

    def pobierz_wszystko(self, trasa, params=None):
        wynik, strona = [], 1
        while True:
            dane, h = self.zadanie('GET', trasa, params={**(params or {}), 'per_page': PER_PAGE, 'page': strona})
            wynik.extend(dane)
            if strona >= int(h.get('X-WP-TotalPages') or 1):
                return wynik
            strona += 1

    def utworz(self, trasa, body):
        return self.zadanie('POST', trasa, body)[0]

    def zaktualizuj(self, trasa, wp_id, body):
        return self.zadanie('POST', f'{trasa}/{wp_id}', body)[0]
