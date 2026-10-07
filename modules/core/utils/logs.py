"""Logi modułu do pliku (E2a): logs/modul-<nazwa>-RRRR-MM-DD_GG-MM-SS.log w katalogu głównym repozytorium.

Folder liczony jest od położenia tego pliku (nie od bieżącego folderu); BM_LOGS_DIR go nadpisuje.
Plik ma limit rozmiaru (rotacja), wiersze dostępu HTTP z werkzeug nie trafiają do pliku, a pliki starsze niż 30 dni
są usuwane przy starcie. W trybie testowym nic nie jest zapisywane.
"""
import logging
import os
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

RETENTION_DAYS = 30
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class _SkipHttpAccess(logging.Filter):
    """Pomija wiersze dostępu HTTP serwera (logger 'werkzeug'), które zapełniałyby plik."""

    def filter(self, record):
        return record.name != 'werkzeug'


def logs_dir():
    override = os.environ.get('BM_LOGS_DIR')
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / 'logs'


def remove_old_logs(directory, now=None, retention_days=RETENTION_DAYS):
    """Usuwa pliki *.log* starsze niż retention_days; zwraca liczbę usuniętych."""
    now = time.time() if now is None else now
    removed = 0
    for path in Path(directory).glob('*.log*'):
        try:
            if path.is_file() and now - path.stat().st_mtime > retention_days * 86400:
                path.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def setup_file_logging(module_name, testing=False):
    """Dodaje do głównego loggera plik logu (poziom INFO). Zwraca ścieżkę pliku albo None.

    Konsola zachowuje dotychczasowy poziom: jeśli moduł ustawił wyższy niż INFO, poziom korzenia schodzi do INFO,
    a istniejące uchwyty (konsola) dostają stary poziom.
    """
    if testing:
        return None
    root = logging.getLogger()
    if any(getattr(h, '_bm_file', False) for h in root.handlers):
        return None
    try:
        directory = logs_dir()
        directory.mkdir(parents=True, exist_ok=True)
        remove_old_logs(directory)
        path = directory / f"modul-{module_name}-{datetime.now():%Y-%m-%d_%H-%M-%S}.log"
        handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding='utf-8')
    except OSError as exc:
        logging.getLogger(__name__).error('Nie można otworzyć pliku logu (logi tylko w konsoli): %s', exc)
        return None
    handler._bm_file = True
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    handler.addFilter(_SkipHttpAccess())
    if root.level > logging.INFO:
        for h in root.handlers:
            if h.level == logging.NOTSET:
                h.setLevel(root.level)
        root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger(__name__).info('Log modułu %s: %s', module_name, path)
    return path
