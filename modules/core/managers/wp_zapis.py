"""W8a: zapis stanu i wyniku meczu z modułu do lokalnego WP (bm-pomocnik, trasa bm/v1/event/<id>/state).

Zasady (plan docs/plan-W8a-W8b.md):
  * Jedno miejsce zapisu. Nasłuch zmian modelu Game (status, home_team_goals, away_team_goals) po zatwierdzeniu transakcji wpisuje mecz do kolejki,
    więc obejmuje WSZYSTKIE miejsca zmiany wyniku/stanu w obu modułach (także przyszłe). Zapisy wykonywane w bez_zapisu_do_wp() (odczyt z WP, importy)
    nie trafiają do kolejki: ochrona przed pętlą WP -> moduł -> WP.
  * Kolejka jest w osobnym pliku SQLite (instance/wp_kolejka.db), bez migracji baz modułów. Wpis na mecz: liczy się ostatni stan (zmiany się łączą);
    treść zapisu (stan, wynik) jest budowana z bazy w chwili wysyłania; numer zapisu seq rośnie przy każdej zmianie (idempotencja po stronie WP).
  * Wysyłanie asynchroniczne w wątku w tle, z limitem czasu zapytania i ponawianiem (2 s, 5 s, 15 s, 60 s, dalej co 60 s). Awaria WP nigdy nie blokuje panelu.
  * Wyłącznik zapisu (instance/wp_zapis.json): wyłączony = kolejka gromadzi, nic nie wychodzi; po włączeniu wychodzi ostatni stan.
  * Zapis działa tylko dla bazy operacyjnej (database.db) w konfiguracji produkcyjnej; bazy próbne (database-proba.db) i testy go nie włączają,
    chyba że jawnie (BM_WP_ZAPIS_PROBA=1 albo app.config['WP_ZAPIS_FORCE']). BM_WP_ZAPIS=0 wyłącza zawsze."""
import contextlib
import contextvars
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_wyciszony = contextvars.ContextVar('bm_wp_zapis_wyciszony', default=False)
BACKOFF_S = (2, 5, 15, 60)
LIMIT_CZASU_S = 3
STANY = {0: 'nierozpoczety', 1: 'trwa', 2: 'zakonczony'}      # Game.STATUS_NOT_STARTED / PENDING / FINISHED


@contextlib.contextmanager
def bez_zapisu_do_wp():
    """Zmiany modelu Game w tym bloku (odczyt z WP, importy, przygotowanie baz próbnych) nie trafiają do kolejki zapisu do WP."""
    token = _wyciszony.set(True)
    try:
        yield
    finally:
        _wyciszony.reset(token)


class Kolejka:
    """Kolejka zapisu: jeden wiersz na mecz (plik SQLite poza bazą modułu)."""

    def __init__(self, sciezka):
        self.sciezka = str(sciezka)
        self._lock = threading.Lock()
        Path(self.sciezka).parent.mkdir(parents=True, exist_ok=True)
        with self._polacz() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS mecze (
                game_id INTEGER PRIMARY KEY, seq INTEGER NOT NULL DEFAULT 0, wyslano_seq INTEGER NOT NULL DEFAULT 0, zgloszono REAL,
                proba INTEGER NOT NULL DEFAULT 0, nastepna REAL NOT NULL DEFAULT 0, blad TEXT, blad_czas REAL,
                odrzucone TEXT, odrzucone_czas REAL, znany TEXT)''')
            c.execute('CREATE TABLE IF NOT EXISTS meta (klucz TEXT PRIMARY KEY, wartosc TEXT)')

    def _polacz(self):
        c = sqlite3.connect(self.sciezka, timeout=5)
        c.row_factory = sqlite3.Row
        return c

    def zglos(self, game_id, teraz):
        with self._lock, self._polacz() as c:
            c.execute('INSERT OR IGNORE INTO mecze (game_id) VALUES (?)', (game_id,))
            c.execute('''UPDATE mecze SET seq = seq + 1, proba = 0, nastepna = ?, odrzucone = NULL, odrzucone_czas = NULL,
                         zgloszono = CASE WHEN seq = wyslano_seq OR zgloszono IS NULL THEN ? ELSE zgloszono END WHERE game_id = ?''', (teraz, teraz, game_id))

    def do_wyslania(self, teraz):
        with self._lock, self._polacz() as c:
            return [dict(r) for r in c.execute('SELECT * FROM mecze WHERE seq > wyslano_seq AND nastepna <= ? ORDER BY game_id', (teraz,))]

    def oznacz_ok(self, game_id, seq, znany, teraz):
        with self._lock, self._polacz() as c:
            c.execute('UPDATE mecze SET wyslano_seq = MAX(wyslano_seq, ?), znany = ? WHERE game_id = ?', (seq, json.dumps(znany) if znany is not None else None, game_id))
            c.execute('UPDATE mecze SET proba = 0, blad = NULL, blad_czas = NULL WHERE game_id = ? AND seq = wyslano_seq', (game_id,))
            c.execute("INSERT OR REPLACE INTO meta (klucz, wartosc) VALUES ('ostatni_ok', ?)", (str(teraz),))

    def oznacz_pominiety(self, game_id, seq):
        with self._lock, self._polacz() as c:
            c.execute('UPDATE mecze SET wyslano_seq = MAX(wyslano_seq, ?) WHERE game_id = ?', (seq, game_id))

    def oznacz_odrzucony(self, game_id, seq, powod, teraz):
        with self._lock, self._polacz() as c:
            c.execute('UPDATE mecze SET wyslano_seq = MAX(wyslano_seq, ?), odrzucone = ?, odrzucone_czas = ?, blad = NULL, blad_czas = NULL, proba = 0 WHERE game_id = ?',
                      (seq, powod, teraz, game_id))

    def oznacz_blad(self, game_id, tekst, teraz):
        with self._lock, self._polacz() as c:
            r = c.execute('SELECT proba FROM mecze WHERE game_id = ?', (game_id,)).fetchone()
            proba = (r['proba'] if r else 0)
            c.execute('UPDATE mecze SET proba = ?, nastepna = ?, blad = ?, blad_czas = ? WHERE game_id = ?',
                      (proba + 1, teraz + BACKOFF_S[min(proba, len(BACKOFF_S) - 1)], tekst, teraz, game_id))

    def ponow_teraz(self, teraz):
        with self._lock, self._polacz() as c:
            c.execute('UPDATE mecze SET nastepna = ? WHERE seq > wyslano_seq', (teraz,))

    def niewyslane(self):
        """[(game_id, ostatni błąd albo None)] dla meczów z niewysłanymi zmianami (kolejki nie ruszamy)."""
        with self._lock, self._polacz() as c:
            return [(r['game_id'], r['blad']) for r in c.execute('SELECT game_id, blad FROM mecze WHERE seq > wyslano_seq ORDER BY game_id')]

    def znany(self, game_id):
        with self._lock, self._polacz() as c:
            r = c.execute('SELECT znany FROM mecze WHERE game_id = ?', (game_id,)).fetchone()
        return json.loads(r['znany']) if r and r['znany'] else None

    def status(self, teraz):
        with self._lock, self._polacz() as c:
            oczekujace = [dict(r) for r in c.execute('SELECT * FROM mecze WHERE seq > wyslano_seq')]
            odrzucone = [dict(r) for r in c.execute('SELECT game_id, odrzucone, odrzucone_czas FROM mecze WHERE odrzucone IS NOT NULL ORDER BY odrzucone_czas DESC')]
            ok = c.execute("SELECT wartosc FROM meta WHERE klucz = 'ostatni_ok'").fetchone()
        blad = max((r for r in oczekujace if r['blad']), key=lambda r: r['blad_czas'] or 0, default=None)
        najstarszy = min((r['zgloszono'] for r in oczekujace if r['zgloszono']), default=None)
        return {
            'w_kolejce': len(oczekujace),
            'najstarszy_s': round(teraz - najstarszy, 1) if najstarszy else 0,
            'ostatni_blad': ({'tekst': blad['blad'], 'czas': blad['blad_czas']} if blad else None),
            'ostatni_ok': float(ok['wartosc']) if ok else None,
            'odrzucone': [{'game_id': r['game_id'], 'powod': r['odrzucone'], 'czas': r['odrzucone_czas']} for r in odrzucone],
        }


class WpZapis:
    def __init__(self, app, kolejka_sciezka, ustawienia_sciezka, klient_fabryka, skonfigurowany, zegar=time.time, powod='', adres='', wersja=''):
        self.app = app
        self.powod, self.adres, self.wersja = powod, adres, wersja     # tylko do pokazania w statusie (panel, samokontrola)
        self._kolejka_sciezka = kolejka_sciezka
        self._kolejka = None
        self.ustawienia = Path(ustawienia_sciezka)
        self.klient_fabryka = klient_fabryka
        self.skonfigurowany = bool(skonfigurowany)
        self.zegar = zegar
        self._stop = threading.Event()
        self._watek = None
        self._wysylka = threading.RLock()                     # jeden przebieg wysyłania naraz (wątek w tle i „wyślij zaległe” przed pobraniem z WP)

    @property
    def kolejka(self):
        """Plik kolejki powstaje dopiero przy pierwszym użyciu (moduł bez aktywnego zapisu, testy i próby nie zostawiają pustych plików w instance)."""
        if self._kolejka is None:
            self._kolejka = Kolejka(self._kolejka_sciezka)
        return self._kolejka

    # -- wyłącznik
    def wlaczony(self):
        try:
            return bool(json.loads(self.ustawienia.read_text(encoding='utf-8')).get('wlaczony', True))
        except (OSError, ValueError):
            return True

    def ustaw_wlaczony(self, wartosc):
        self.ustawienia.parent.mkdir(parents=True, exist_ok=True)
        self.ustawienia.write_text(json.dumps({'wlaczony': bool(wartosc)}), encoding='utf-8')

    # -- wejście z nasłuchu
    def zglos(self, game_id):
        self.kolejka.zglos(int(game_id), self.zegar())

    # -- treść zapisu budowana z bazy w chwili wysyłania
    def _zadanie(self, game_id):
        """None = mecz bez powiązania z WP (pomijany); str = powód odrzucenia (np. brak wyniku); słownik = treść zapisu bez seq."""
        from core.models.base_game import get_game_model
        from core.models.base_scraper import get_scraper_model
        Game = get_game_model()
        game = Game.query.get(game_id)
        if game is None:
            return None
        scraper = get_scraper_model().get_by_folder('wp')
        wp_id = game.get_foreign_id(scraper.id) if scraper else None
        if not wp_id:
            return None
        stan = STANY.get(game.status)
        if stan is None:
            return None
        home, away = game.home_team_goals, game.away_team_goals
        if stan == 'nierozpoczety':
            home = away = None
        elif stan == 'zakonczony' and (home is None or away is None):
            return 'Mecz zakończony bez wyniku: uzupełnij wynik'
        elif stan == 'trwa' and (home is None or away is None):
            home = away = None
        zad = {'wp_id': str(wp_id), 'state': stan, 'home': home, 'away': away}
        karne = getattr(game, 'shootout', None)
        if stan == 'zakonczony' and karne is not None:                     # konkurs rzutów karnych: WP wylicza zwycięzcę (wynik, a przy remisie konkurs)
            zad['pen_home'], zad['pen_away'] = karne.home_team_shootouts, karne.away_team_shootouts
        return zad

    def _obsluz(self, wiersz, teraz):
        from core.extensions import db
        from core.managers.wp_client import WpError
        gid, seq = wiersz['game_id'], wiersz['seq']
        with self.app.app_context():
            try:
                zad = self._zadanie(gid)
            finally:
                db.session.remove()
        if zad is None:
            self.kolejka.oznacz_pominiety(gid, seq)
            return 0
        if isinstance(zad, str):
            self.kolejka.oznacz_odrzucony(gid, seq, zad, teraz)
            return 0
        tresc = {k: zad[k] for k in ('state', 'home', 'away', 'pen_home', 'pen_away') if k in zad}
        if self.kolejka.znany(gid) == tresc:                               # WP już ma ten stan: nie wysyłamy drugi raz
            self.kolejka.oznacz_ok(gid, seq, tresc, teraz)
            return 0
        try:
            odp = self.klient_fabryka().post_json(f"bm/v1/event/{zad['wp_id']}/state", {**tresc, 'seq': seq})
        except WpError as e:
            if e.kind == 'conflict':
                self.kolejka.oznacz_odrzucony(gid, seq, f'WP odrzucił zapis: {e}', teraz)
            else:
                self.kolejka.oznacz_blad(gid, str(e), teraz)
            return 0
        except Exception as e:                                             # np. nieoczekiwany błąd klienta: ponawiamy, nie blokujemy
            self.kolejka.oznacz_blad(gid, f'błąd zapisu do WP: {e}', teraz)
            return 0
        self.kolejka.oznacz_ok(gid, seq, tresc, teraz)
        return 1

    def przetworz_raz(self, teraz=None):
        """Jeden przebieg kolejki (wątek w tle woła go w pętli; testy wołają bezpośrednio). Zwraca liczbę wysłanych zapisów."""
        if not self.skonfigurowany or not self.wlaczony():
            return 0
        teraz = self.zegar() if teraz is None else teraz
        with self._wysylka:
            return sum(self._obsluz(w, teraz) for w in self.kolejka.do_wyslania(teraz))

    def ponow_teraz(self):
        self.kolejka.ponow_teraz(self.zegar())

    def wyslij_zalegle(self):
        """Przed pobraniem z WP: próbuje wysłać WSZYSTKIE zaległe zapisy (jak „Wyślij teraz”), niczego z kolejki nie usuwa. Zwraca
        {'niewyslane': {game_id: powód}, 'aktywny': bool}: mecze, dla których po tej próbie nadal są niewysłane zmiany, oraz czy zapis w ogóle działa."""
        if not self.skonfigurowany:
            return {'niewyslane': {}, 'aktywny': False}
        with self._wysylka:
            self.kolejka.ponow_teraz(self.zegar())
            try:
                self.przetworz_raz()
            except Exception as e:
                logger.warning(f'Zapis do WP: błąd wysyłania zaległych zapisów przed pobraniem: {e}')
        wlaczony = self.wlaczony()
        powody = {gid: ('zapis do WP jest wyłączony' if not wlaczony else (blad or 'WP nie odpowiada')) for gid, blad in self.kolejka.niewyslane()}
        return {'niewyslane': powody, 'aktywny': wlaczony}

    def status(self):
        if not self.skonfigurowany:
            return self.status_nieaktywny(self.powod)
        s = self.kolejka.status(self.zegar())
        s.update({'skonfigurowany': self.skonfigurowany, 'wlaczony': self.wlaczony(), 'powod': '', 'adres': self.adres, 'wersja': self.wersja})
        return s

    @staticmethod
    def status_nieaktywny(powod=''):
        return {'skonfigurowany': False, 'wlaczony': False, 'w_kolejce': 0, 'najstarszy_s': 0, 'ostatni_blad': None, 'ostatni_ok': None, 'odrzucone': [],
                'powod': powod or 'zapis do WP nie został zainicjowany', 'adres': '', 'wersja': ''}

    # -- wątek w tle
    def start(self):
        if self._watek is not None or not self.skonfigurowany:
            return

        def petla():
            while not self._stop.wait(0.5):
                try:
                    self.przetworz_raz()
                except Exception as e:                                     # pętla nie może umrzeć
                    logger.warning(f'Zapis do WP: błąd przebiegu kolejki: {e}')
        self._watek = threading.Thread(target=petla, name='wp-zapis', daemon=True)
        self._watek.start()

    def stop(self):
        self._stop.set()


_instancja = None
_nasluch = False


def get_wp_zapis():
    return _instancja


def ustaw_instancje(z):
    global _instancja
    _instancja = z


def _zainstaluj_nasluch():
    """Nasłuch zmian modelu Game na poziomie sesji SQLAlchemy: zbiera mecze ze zmienionym stanem/wynikiem, po zatwierdzeniu wpisuje je do kolejki."""
    global _nasluch
    if _nasluch:
        return
    _nasluch = True
    from sqlalchemy import event, inspect
    from sqlalchemy.orm import Session

    @event.listens_for(Session, 'before_flush')
    def _przed(session, ctx, instances):
        z = _instancja
        if z is None or not z.skonfigurowany or _wyciszony.get():
            return
        try:
            from core.models.base_game import get_game_model
            Game = get_game_model()
        except Exception:
            return
        ids = session.info.setdefault('bm_wp_zapis_ids', set())
        try:
            from core.models.base_shootout import get_shootout_model
            Shootout = get_shootout_model()
        except Exception:
            Shootout = None
        for obj in list(session.new) + list(session.dirty):               # konkurs rzutów karnych: zmiana wyniku konkursu to zmiana meczu
            if Shootout is not None and isinstance(obj, Shootout) and obj.game_id is not None:
                ids.add(obj.game_id)
        for obj in list(session.dirty):
            if isinstance(obj, Game) and obj.id is not None:
                st = inspect(obj)
                if any(st.attrs[a].history.has_changes() for a in ('status', 'home_team_goals', 'away_team_goals')):
                    ids.add(obj.id)

    @event.listens_for(Session, 'after_commit')
    def _po(session):
        ids = session.info.pop('bm_wp_zapis_ids', None)
        z = _instancja
        if ids and z is not None:
            for gid in ids:
                try:
                    z.zglos(gid)
                except Exception as e:
                    logger.warning(f'Zapis do WP: nie udało się dopisać meczu {gid} do kolejki: {e}')

    @event.listens_for(Session, 'after_rollback')
    def _wycofanie(session):
        session.info.pop('bm_wp_zapis_ids', None)


def powod_nieaktywnosci(app, cfg, nazwa_bazy=None):
    """None, gdy zapis do WP ma być aktywny; w przeciwnym razie krótki polski powód (pokazuje go pasek w panelu, log i samokontrola skryptu próby)."""
    forced = app.config.get('WP_ZAPIS_FORCE')
    if forced is not None:
        return None if forced else 'wyłączony ustawieniem aplikacji'
    if os.environ.get('BM_WP_ZAPIS') == '0':
        return 'wyłączony zmienną BM_WP_ZAPIS=0'
    if app.config.get('TESTING'):
        return 'tryb testowy'
    if not cfg.enabled:
        return 'moduł nie ma własnego WP' + (f' ({cfg.problem})' if cfg.problem else '')
    if not cfg.has_auth:
        return f'brak danych logowania do WP (oczekiwany plik {os.path.basename(cfg.creds_file or "dane-api-<moduł>.json")} w folderze {os.path.dirname(cfg.creds_file or "")})'
    if nazwa_bazy is None:
        from core.extensions import db
        nazwa_bazy = os.path.basename(str(db.engine.url.database or ''))
    if nazwa_bazy != 'database.db' and os.environ.get('BM_WP_ZAPIS_PROBA') != '1':
        return f'baza {nazwa_bazy} nie jest bazą operacyjną (database.db); dla próby ustaw BM_WP_ZAPIS_PROBA=1'
    return None


def _skonfigurowany(app, cfg, nazwa_bazy=None):
    return powod_nieaktywnosci(app, cfg, nazwa_bazy) is None


def _commit():
    """Skrócony commit kodu modułu (informacyjnie, do samokontroli; brak gita = '?')."""
    import subprocess
    try:
        kw = dict(cwd=os.path.dirname(os.path.abspath(__file__)), capture_output=True, text=True, timeout=5)
        c = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], **kw).stdout.strip()
        b = subprocess.run(['git', 'branch', '--show-current'], **kw).stdout.strip()
        brudny = bool(subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], **kw).stdout.strip())
        return f'{b or "?"}, {c or "?"}' + ('-dirty' if brudny else '')
    except Exception:
        return '?'


def init_wp_zapis(app):
    """Wołane raz przy starcie modułu (obie fabryki aplikacji): tworzy kolejkę, instaluje nasłuch, w produkcji uruchamia wątek wysyłania."""
    from core.managers.wp_client import WpClient, load_wp_config
    module_dir = app.config.get('MODULE_DIR') or os.getcwd()
    cfg = load_wp_config(module_dir)
    with app.app_context():
        powod = powod_nieaktywnosci(app, cfg)
    skonf = powod is None
    instance = Path(app.instance_path)
    z = WpZapis(app, app.config.get('WP_KOLEJKA_PATH') or instance / 'wp_kolejka.db', app.config.get('WP_ZAPIS_USTAWIENIA') or instance / 'wp_zapis.json',
                lambda: WpClient(load_wp_config(module_dir), timeout=LIMIT_CZASU_S), skonf, powod=powod or '', adres=cfg.url if skonf else '',
                wersja=_commit() if skonf else '')
    ustaw_instancje(z)
    _zainstaluj_nasluch()
    if skonf and not app.config.get('TESTING'):
        z.start()
        logger.info('Zapis do WP: %s -> %s (%s)', 'WŁĄCZONY' if z.wlaczony() else 'WYŁĄCZONY wyłącznikiem', z.adres, z.wersja)
    else:
        logger.info('Zapis do WP: NIEAKTYWNY: %s', powod)
    return z
