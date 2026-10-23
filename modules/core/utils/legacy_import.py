"""Blokada dotychczasowego pobierania danych rozgrywek ze stron (I0).

Dane rozgrywek mają trafiać do modułu wyłącznie z WP/SportsPress (importery ze stron zapisują do WP, moduł tylko czyta). Dotychczasowe
pobieranie w modułach (scrapery NALF, MZPN, Superscore, Łączy nas piłka, kadry od pomocnika, kolejka dopasowań "pending") zostaje w kodzie
jako rezerwa, ale jego trasy są domyślnie zablokowane: odpowiadają 403 z wyjaśnieniem. Awaryjne włączenie: zmienna BM_LEGACY_IMPORT=1
(w konfiguracji LEGACY_IMPORT_ENABLED). Nie ma harmonogramu ani pobierania przy starcie: pobieranie uruchamiały tylko przyciski w panelu.

Blokowane są trasy, których adres zawiera: /scrape, /scrape-, /scrape/, pending-matches, pending-departures, /helper-squad/fetch,
/scraper-data (adresy scraperów lig). Odczyt stanu pobierania (/api/games/scrape/status) pozostaje dozwolony."""
import re

from flask import jsonify, request

BLOCKED = re.compile(r'(/scrape(?:[-/]|$)|pending-matches|pending-departures|/helper-squad/fetch|/scraper-data)')
ALLOWED = ('/api/games/scrape/status',)

MESSAGE = ('Pobieranie danych ze stron jest wyłączone: dane rozgrywek pochodzą z WP (importery ze stron zapisują do WP). '
           'Awaryjnie można je włączyć zmienną BM_LEGACY_IMPORT=1 i restartem modułu.')


def is_blocked_path(path):
    return path not in ALLOWED and bool(BLOCKED.search(path))


def block_legacy_imports(app):
    """Dokłada do aplikacji blokadę tras dotychczasowego pobierania (chyba że LEGACY_IMPORT_ENABLED)."""

    @app.before_request
    def _block_legacy_imports():
        if app.config.get('LEGACY_IMPORT_ENABLED', False):
            return None
        if request.method != 'OPTIONS' and is_blocked_path(request.path):
            app.logger.warning(f'Zablokowano dotychczasowe pobieranie ze stron: {request.method} {request.path}')
            return jsonify({'error': MESSAGE, 'success': False}), 403
        return None
