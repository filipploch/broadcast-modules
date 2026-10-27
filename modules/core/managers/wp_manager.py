"""WpManager (WP-2): połączenie modułu z jego instancją WordPressa, lista rozgrywek i rozgrywki domyślne modułu.

- Stan połączenia i lista rozgrywek odświeżają się w tle (co minutę, przy błędzie co 10 s) i na prośbę operatora; WP nie wpływa
  na transmisję: każdy błąd to tylko stan w panelu i żółty pasek.
- Rozgrywki domyślne i ostatnia pobrana lista leżą w pliku instance/wp_rozgrywki.json modułu (ustawienie lokalne, bez zmiany schematu bazy).
- Jedna rozgrywka na liście = przypisana automatycznie jako domyślna (gdy nie ma jeszcze domyślnej). Zapisana para, której już nie ma
  w WP, jest zgłaszana, ale nigdy po cichu nie zmieniana."""
import json
import os
import threading
import time
from datetime import datetime

from core.managers.wp_client import WpClient, WpError, fetch_competitions
from core.managers.wp_pull import pobierz_pare

INTERVAL_OK_S = 60      # pełne odświeżenie listy przy działającym połączeniu
INTERVAL_FAIL_S = 10    # krok pętli: lekki ping (połączenie działa) albo ponowna próba (brak połączenia)

NOTICE_DEFAULT_MISSING = 'wp-default-missing'
NOTICE_CHOICE = 'wp-choice'


class WpManager:
    def __init__(self, cfg, store_path, socketio=None, notices=None, logger=None, client=None):
        self.cfg = cfg
        self.store_path = str(store_path)
        self.socketio = socketio
        self.notices = notices
        self.log = logger
        self.client = client or WpClient(cfg)
        self.interval_ok = INTERVAL_OK_S
        self.interval_fail = INTERVAL_FAIL_S
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._last_full = 0.0
        stored = self._load()
        self._default = stored.get('default')
        self._list = stored.get('list')                 # ostatnia pobrana lista (kopia na czas braku połączenia)
        self._pull = stored.get('pull')                 # wynik ostatniego podglądu albo pobrania (W7a)
        self._last_apply_at = stored.get('last_apply_at', '')
        self._pulling = False
        self._connected = None                          # None = jeszcze nie sprawdzono
        self._error = ''
        self._error_kind = ''
        self._checked_at = ''
        self._last_emitted = None

    # -- trwałe ustawienia
    def _load(self):
        try:
            with open(self.store_path, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self):
        tmp = self.store_path + '.tmp'
        try:
            os.makedirs(os.path.dirname(self.store_path) or '.', exist_ok=True)
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'default': self._default, 'list': self._list, 'pull': self._pull, 'last_apply_at': self._last_apply_at}, f,
                          ensure_ascii=False, indent=2)
            os.replace(tmp, self.store_path)
        except OSError as e:
            self._warn(f'WP: nie udało się zapisać {self.store_path}: {e}')

    def _warn(self, msg):
        if self.log:
            self.log.warning(msg)

    # -- stan dla panelu
    def state(self):
        with self._lock:
            items = (self._list or {}).get('items', [])
            keys = {i['key'] for i in items}
            d = self._default
            return {
                'enabled': self.cfg.enabled,
                'problem': self.cfg.problem,
                'module_id': self.cfg.module_id,
                'title': self.cfg.title,
                'url': self.cfg.url,
                'has_auth': self.cfg.has_auth,
                'connected': self._connected,
                'error': self._error,
                'error_kind': self._error_kind,
                'checked_at': self._checked_at,
                'from_cache': bool(self._list) and self._connected is not True,
                'fetched_at': (self._list or {}).get('fetched_at', ''),
                'items': items,
                'unassigned': (self._list or {}).get('unassigned', 0),
                'default': d,
                'default_missing': bool(d) and bool(self._list) and d['key'] not in keys,
                'needs_choice': d is None and len(items) > 1,
                'no_competitions': self._connected is True and not items,
                'pull': self._pull,
                'pulling': self._pulling,
                'last_apply_at': self._last_apply_at,
            }

    def _publish(self):
        st = self.state()
        sig = json.dumps({k: v for k, v in st.items() if k not in ('checked_at', 'fetched_at')}, sort_keys=True, ensure_ascii=False)
        if sig != self._last_emitted:
            self._last_emitted = sig
            if self.socketio is not None:
                try:
                    self.socketio.emit('wp_state', st)
                except Exception as e:
                    self._warn(f'WP: nie udało się wysłać stanu do paneli: {e}')
        self._sync_notices(st)
        return st

    def _sync_notices(self, st):
        n = self.notices
        if n is None or not self.cfg.enabled:
            return
        try:
            if st['connected'] is False:
                n.on_service_event('wp-link', 'warning', st['error'] or 'brak połączenia z WP')
            elif st['connected'] is True:
                n.on_service_event('wp-link', 'recovered', '')
            if st['default_missing']:
                d = st['default']
                n.set(NOTICE_DEFAULT_MISSING, f'WP: zapisanych rozgrywek ({d["league_name"]}, {d["season_name"]}) nie ma już w WP: wybierz ponownie',
                      'warning')
            else:
                n.clear(NOTICE_DEFAULT_MISSING)
            if st['needs_choice']:
                n.set(NOTICE_CHOICE, 'WP: wybierz rozgrywki modułu (Dane wspólne, Rozgrywki WP)', 'info')
            else:
                n.clear(NOTICE_CHOICE)
        except Exception as e:
            self._warn(f'WP: nie udało się zaktualizować komunikatów: {e}')

    # -- odświeżanie
    def refresh(self):
        """Pobiera listę rozgrywek z WP (blokująco). Zwraca stan. Bezpieczne do wołania z wielu wątków."""
        if not self.cfg.enabled:
            return self.state()
        with self._refresh_lock:
            now = datetime.now().isoformat(timespec='seconds')
            try:
                data = fetch_competitions(self.client)
            except WpError as e:
                with self._lock:
                    self._connected, self._error, self._error_kind, self._checked_at = False, str(e), e.kind, now
                return self._publish()
            except Exception as e:                                   # nieoczekiwany błąd nie może zabić wątku odświeżania
                with self._lock:
                    self._connected, self._error, self._error_kind, self._checked_at = False, f'błąd odczytu z WP: {e}', 'format', now
                self._warn(f'WP: nieoczekiwany błąd odczytu: {e}')
                return self._publish()
            with self._lock:
                self._connected, self._error, self._error_kind, self._checked_at = True, '', '', now
                self._list = data
                items = data['items']
                if self._default is None and len(items) == 1:
                    self._default = self._make_default(items[0], auto=True)
                self._save()
            return self._publish()

    def check_link(self):
        """Lekki ping przy działającym połączeniu: wykrywa utratę WP w kilka sekund bez pobierania całej listy."""
        if not self.cfg.enabled:
            return self.state()
        try:
            self.client.ping()
        except WpError as e:
            with self._lock:
                self._connected, self._error, self._error_kind = False, str(e), e.kind
                self._checked_at = datetime.now().isoformat(timespec='seconds')
            return self._publish()
        except Exception as e:
            self._warn(f'WP: nieoczekiwany błąd pingu: {e}')
        return self.state()

    @staticmethod
    def _make_default(item, auto):
        keep = ('key', 'league_id', 'season_id', 'league_name', 'league_slug', 'season_name', 'season_slug')
        d = {k: item[k] for k in keep}
        d['auto'] = auto
        d['saved_at'] = datetime.now().isoformat(timespec='seconds')
        return d

    # -- wybór rozgrywek domyślnych
    def set_default(self, league_id, season_id):
        """Zapisuje parę jako domyślną. Para musi być na liście z WP. Zwraca (ok, komunikat)."""
        key = f'{int(league_id)}:{int(season_id)}'
        with self._lock:
            items = (self._list or {}).get('items', [])
            item = next((i for i in items if i['key'] == key), None)
            if item is None:
                return False, 'tych rozgrywek nie ma na liście z WP (odśwież listę)'
            self._default = self._make_default(item, auto=False)
            self._save()
        self._publish()
        return True, ''

    def clear_default(self):
        with self._lock:
            self._default = None
            self._save()
        self._publish()

    # -- pobieranie pary z WP do bazy modułu (W7a)
    def pull(self, apply, db, logo_root, logo_folder, kopie_dir, league_id=None, season_id=None):
        """Podgląd (apply=False) albo zapis zaznaczonej pary (domyślnie rozgrywki domyślne modułu). Blokuje do końca; nie zgłasza wyjątków.
        Wynik: {'ok', 'zapisano', 'raport'|'blad', 'key', 'at', 'apply'}; ostatni wynik zostaje w stanie (state()['pull'])."""
        if not self.cfg.enabled:
            return {'ok': False, 'zapisano': False, 'blad': 'Ten moduł nie ma własnej instancji WP'}
        with self._lock:
            d = self._default
            if league_id is None or season_id is None:
                if not d:
                    return {'ok': False, 'zapisano': False, 'blad': 'Najpierw wybierz rozgrywki (Rozgrywki WP)'}
                league_id, season_id = d['league_id'], d['season_id']
            item = next((i for i in (self._list or {}).get('items', []) if i['league_id'] == int(league_id) and i['season_id'] == int(season_id)), None)
            self._pulling = True
        self._publish()
        try:
            wynik = pobierz_pare(self.client, db, int(league_id), int(season_id), logo_root, logo_folder, kopie_dir, apply)
        finally:
            with self._lock:
                self._pulling = False
        at = datetime.now().isoformat(timespec='seconds')
        wynik.update(key=f'{int(league_id)}:{int(season_id)}', at=at, apply=bool(apply),
                     label=f'{item["league_name"]} — {item["season_name"]}' if item else '')
        with self._lock:
            self._pull = wynik
            if wynik.get('ok') and apply:
                self._last_apply_at = at
            self._save()
        self._publish()
        return wynik

    # -- tło
    def start(self):
        if not self.cfg.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name='wp-manager', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def request_refresh(self):
        """Odświeżenie w tle na prośbę operatora (nie blokuje obsługi zdarzenia)."""
        threading.Thread(target=self.refresh, name='wp-refresh', daemon=True).start()

    def _run(self):
        while not self._stop.is_set():
            if not self._connected or time.monotonic() - self._last_full >= self.interval_ok:
                self.refresh()
                self._last_full = time.monotonic()
            else:
                self.check_link()
            self._wake.wait(self.interval_fail)
            self._wake.clear()
