"""Logi modułu do pliku (E2a): osobny plik modul-<nazwa>.log w folderze uruchomienia logs/logs-RRRR-MM-DD-gg-mm-ss/.

Folder uruchomienia zakłada HUB i przekazuje jego ścieżkę zmienną środowiskową BM_LOG_RUN_DIR (obok są pliki pluginów).
Moduł uruchomiony osobno (bez zmiennej) zakłada własny folder w tym samym formacie. Folder główny logów jest liczony od
położenia tego pliku (nie od bieżącego folderu); BM_LOGS_DIR go nadpisuje.

Plik ma limit rozmiaru (rotacja), wiersze dostępu HTTP z werkzeug nie trafiają do pliku, a całe foldery uruchomień
starsze niż 30 dni są usuwane przy starcie. Znacznik czasu ma milisekundy i ten sam format co w HUB-ie i pluginach:
"RRRR-MM-DD gg:mm:ss.mmm". W trybie testowym nic nie jest zapisywane.
"""
import logging
import os
import shutil
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

RETENTION_DAYS = 30
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3
RUN_DIR_ENV = 'BM_LOG_RUN_DIR'
RUN_DIR_PREFIX = 'logs-'
RUN_DIR_FORMAT = 'logs-%Y-%m-%d-%H-%M-%S'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
# Jednolity format ze znacznikiem czasu z milisekundami (konsola i plik modułu)
CONSOLE_FORMAT = '%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s'
FILE_FORMAT = '%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s'


class _SkipHttpAccess(logging.Filter):
    """Pomija wiersze dostępu HTTP serwera (logger 'werkzeug'), które zapełniałyby plik."""

    def filter(self, record):
        return record.name != 'werkzeug'


def logs_root():
    override = os.environ.get('BM_LOGS_DIR')
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / 'logs'


def run_dir(now=None):
    """Folder bieżącego uruchomienia: z BM_LOG_RUN_DIR (założony przez HUB) albo własny w tym samym formacie."""
    given = os.environ.get(RUN_DIR_ENV)
    if given:
        path = Path(given)
    else:
        path = logs_root() / (now or datetime.now()).strftime(RUN_DIR_FORMAT)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _newest_mtime(directory):
    newest = directory.stat().st_mtime
    for child in directory.iterdir():
        try:
            newest = max(newest, child.stat().st_mtime)
        except OSError:
            pass
    return newest


def remove_old_run_dirs(root, now=None, retention_days=RETENTION_DAYS):
    """Usuwa całe foldery uruchomień (logs-*), w których nic nie zmieniono od ponad retention_days; zwraca ich liczbę."""
    now = time.time() if now is None else now
    removed = 0
    root = Path(root)
    if not root.is_dir():
        return 0
    for directory in root.iterdir():
        try:
            if (directory.is_dir() and directory.name.startswith(RUN_DIR_PREFIX)
                    and now - _newest_mtime(directory) > retention_days * 86400):
                shutil.rmtree(directory)
                removed += 1
        except OSError:
            pass
    return removed


def file_formatter():
    return logging.Formatter(FILE_FORMAT, DATE_FORMAT)


def setup_file_logging(module_name, testing=False):
    """Dodaje do głównego loggera plik logu (poziom INFO). Zwraca ścieżkę pliku albo None.

    Konsola zachowuje dotychczasowy poziom: jeśli moduł ustawił wyższy niż INFO, poziom korzenia schodzi do INFO,
    a istniejące uchwyty (konsola) dostają stary poziom. Restart modułu w tym samym folderze dopisuje do tego samego
    pliku, poprzedzając wpis wierszem rozdzielającym.
    """
    if testing:
        return None
    root = logging.getLogger()
    if any(getattr(h, '_bm_file', False) for h in root.handlers):
        return None
    try:
        remove_old_run_dirs(logs_root())
        directory = run_dir()
        path = directory / f'modul-{module_name}.log'
        existed = path.exists() and path.stat().st_size > 0
        handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding='utf-8')
    except OSError as exc:
        logging.getLogger(__name__).error('Nie można otworzyć pliku logu (logi tylko w konsoli): %s', exc)
        return None
    handler._bm_file = True
    handler.setLevel(logging.INFO)
    handler.setFormatter(file_formatter())
    handler.addFilter(_SkipHttpAccess())
    if root.level > logging.INFO:
        for h in root.handlers:
            if h.level == logging.NOTSET:
                h.setLevel(root.level)
        root.setLevel(logging.INFO)
    root.addHandler(handler)
    log = logging.getLogger(__name__)
    # Potomek przeładowania serwera deweloperskiego (werkzeug) to ten sam start, a nie restart modułu
    if existed and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        log.info('──────── ponowne uruchomienie składnika modul-%s ────────', module_name)
    log.info('Log modułu %s: %s', module_name, path)
    return path
