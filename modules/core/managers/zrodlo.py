"""Pobieranie wyników ze źródła zewnętrznego (W8a2): źródło -> WP -> moduł jednym przyciskiem „Pobierz”.

    pobierz(wyniki, liga) = lekki import do WP (tools/import_wp/odswiez.py w PODPROCESIE, limit 120 s, blokada pliku przed podwójnym uruchomieniem)
                            + automatyczne „Pobierz z WP” tej samej pary (kopia bazy, zaległa kolejka zapisu idzie przed pobraniem).

Źródło deklaruje plik source.json obok module.json: {"typ": "nalffutsal" | "superscore" | "brak"}. Bez źródła (typ "brak" albo brak pliku) przycisk jest ukryty.
(Nie w module.json: HUB czyta module.json ściśle i odrzuca moduł z nieznanym polem.)
Liga i sezon w źródle wynikają ze slugów w WP (nalf-l19, nalf-s61); parę (liga WP, sezon WP) daje LeagueForeignId ligi modułu albo wybór domyślny rozgrywek.
Praca idzie w wątku (klik nie blokuje panelu); panel odpytuje stan trasą /api/zrodlo/status. Nic nie działa w tle bez kliknięcia."""
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

TIMEOUT_S = 120
TYPY = ('nalffutsal', 'superscore')
PREFIKS = {'nalffutsal': 'nalf', 'superscore': 'superscore'}          # prefiks slugów ligi/sezonu w WP dla danego typu źródła


def wczytaj_blok_zrodla(module_dir):
    """(typ, id modułu): typ z <module_dir>/source.json, id z module.json; typ 'brak', gdy pliku nie ma, jest uszkodzony albo typ jest nieznany. Nigdy nie zgłasza wyjątku."""
    def czytaj(nazwa):
        try:
            d = json.loads((Path(module_dir) / nazwa).read_text(encoding='utf-8-sig'))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}
    typ = str(czytaj('source.json').get('typ') or 'brak')
    return (typ if typ in TYPY else 'brak'), str(czytaj('module.json').get('id') or '')


def id_ze_sluga(slug, prefiks, litera):
    """'nalf-l19' -> '19' (litera 'l' = liga, 's' = sezon); None, gdy slug nie pasuje do źródła."""
    m = re.fullmatch(rf'{re.escape(prefiks)}-{litera}(.+)', slug or '')
    return m.group(1) if m else None


class Zrodlo:
    def __init__(self, module_dir, repo_root=None, python=None, uruchom=None, zegar=time.time):
        self.module_dir = str(module_dir)
        self.repo_root = Path(repo_root) if repo_root else Path(self.module_dir).resolve().parents[1]
        self.python = python or sys.executable
        self.uruchom = uruchom or self._uruchom_podproces
        self.zegar = zegar
        self.typ, self.modul_id = wczytaj_blok_zrodla(self.module_dir)
        self._lock = threading.Lock()
        self._stan = {'w_toku': False, 'etap': '', 'liga': '', 'start': None, 'wynik': None}

    # -- dostępność
    def dostepne(self, wp_enabled=True):
        """(czy pokazać przycisk, powód ukrycia)."""
        if self.typ == 'brak':
            return False, 'ten moduł nie ma źródła zewnętrznego'
        if not wp_enabled:
            return False, 'ten moduł nie ma własnej instancji WP'
        return True, ''

    def status(self, wp_enabled=True):
        dost, powod = self.dostepne(wp_enabled)
        with self._lock:
            s = dict(self._stan)
        s.update(typ=self.typ, dostepne=dost, powod=powod)
        if s['start'] and s['w_toku']:
            s['trwa_s'] = round(self.zegar() - s['start'], 1)
        return s

    # -- para (liga WP, sezon WP) i identyfikatory w źródle
    def rozwiaz(self, league_id, wp_state, powiazanie):
        """Zwraca ({'liga_wp','sezon_wp','liga','sezon','nazwa'}, None) albo (None, komunikat).
        powiazanie: klucz 'liga_wp:sezon_wp' ligi modułu (LeagueForeignId) albo None; bez ligi - wybór domyślny rozgrywek."""
        klucz = powiazanie
        if league_id is not None and not klucz:
            return None, 'Ta liga nie pochodzi z WP: najpierw „Pobierz z WP” (strona Rozgrywki WP).'
        if klucz is None:
            d = wp_state.get('default')
            if not d:
                return None, 'Najpierw wybierz rozgrywki (Rozgrywki WP).'
            klucz = d['key']
        item = next((i for i in wp_state.get('items') or [] if i.get('key') == klucz), None)
        if item is None:
            return None, 'Tych rozgrywek nie ma na liście z WP (odśwież listę rozgrywek).'
        prefiks = PREFIKS.get(self.typ)
        liga, sezon = id_ze_sluga(item.get('league_slug'), prefiks, 'l'), id_ze_sluga(item.get('season_slug'), prefiks, 's')
        if not liga or not sezon:
            return None, f'Rozgrywki „{item.get("league_name", "")}” nie pochodzą ze źródła tego modułu ({self.typ}).'
        return {'liga_wp': int(item['league_id']), 'sezon_wp': int(item['season_id']), 'liga': liga, 'sezon': sezon,
                'nazwa': f'{item.get("league_name", "")} — {item.get("season_name", "")}'}, None

    # -- podproces z lekkim importem
    def _uruchom_podproces(self, para):
        """Uruchamia tools/import_wp/odswiez.py --json i zwraca słownik z jego ostatniej linii (limit TIMEOUT_S)."""
        skrypt = self.repo_root / 'tools' / 'import_wp' / 'odswiez.py'
        if not skrypt.is_file():
            return {'ok': False, 'blad': f'Brak narzędzia importu ({skrypt.name}) w tej wersji.'}
        polecenie = [self.python, str(skrypt), self.modul_id, '--liga', para['liga'], '--sezon', para['sezon'], '--json']
        cache = os.environ.get('BM_ZRODLO_CACHE')                      # tylko próby ręczne: udawane źródło z katalogu (produkcja czyta źródło na żywo)
        if cache:
            polecenie += ['--cache', cache, '--stare-dane-ok']
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        try:
            r = subprocess.run(polecenie, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=TIMEOUT_S, env=env,
                               cwd=str(self.repo_root), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            return {'ok': False, 'blad': f'Przekroczono limit czasu {TIMEOUT_S} s: import przerwany, w WP mogło zostać część zmian (powtórz „Pobierz”).'}
        except OSError as e:
            return {'ok': False, 'blad': f'Nie udało się uruchomić importu: {e}'}
        linie = [l for l in (r.stdout or '').splitlines() if l.strip().startswith('{')]
        if linie:
            try:
                return json.loads(linie[-1])
            except ValueError:
                pass
        return {'ok': False, 'blad': 'Import zakończył się bez wyniku: ' + ((r.stderr or r.stdout or '').strip()[-300:] or f'kod {r.returncode}')}

    # -- uruchomienie
    def start(self, para, wykonaj_pobranie, opis_ligi=''):
        """Rozpoczyna pracę w wątku. wykonaj_pobranie(para) -> wynik „Pobierz z WP” (słownik z WpManager.pull). Zwraca (ok, komunikat)."""
        with self._lock:
            if self._stan['w_toku']:
                return False, 'Pobieranie już trwa.'
            self._stan = {'w_toku': True, 'etap': 'źródło', 'liga': opis_ligi or para['nazwa'], 'start': self.zegar(), 'wynik': None}
        threading.Thread(target=self._praca, args=(para, wykonaj_pobranie), name='zrodlo-pobierz', daemon=True).start()
        return True, ''

    def _etap(self, nazwa):
        with self._lock:
            self._stan['etap'] = nazwa

    def _praca(self, para, wykonaj_pobranie):
        t0 = self.zegar()
        wynik = {'ok': False, 'zrodlo': None, 'modul': None, 'blad': '', 'czas_s': 0}
        try:
            try:
                zr = self.uruchom(para)
            except Exception as e:                                        # błąd narzędzia nie może zabić wątku
                zr = {'ok': False, 'blad': f'Błąd importu: {e}'}
            wynik['zrodlo'] = zr
            zajete = 'już trwa' in (zr.get('blad') or '')
            if not zajete:
                self._etap('moduł')
                try:
                    wynik['modul'] = wykonaj_pobranie(para)
                except Exception as e:
                    logger.warning(f'Pobierz: błąd pobierania z WP: {e}')
                    wynik['modul'] = {'ok': False, 'blad': f'Błąd pobierania z WP: {e}'}
            wynik['ok'] = bool(zr.get('ok')) and bool((wynik['modul'] or {}).get('ok'))
            wynik['blad'] = zr.get('blad') or ((wynik['modul'] or {}).get('blad') or '')
        finally:
            wynik['czas_s'] = round(self.zegar() - t0, 1)
            wynik['tekst'] = podsumowanie(wynik)
            with self._lock:
                self._stan.update(w_toku=False, etap='', wynik=wynik)


def podsumowanie(w):
    """Tekst okna po pobraniu: część ze źródła (zmienione, pominięte przez flagę, zniklych, błędy) i część modułu (co zmieniło się w bazie, kopia)."""
    z, m = w.get('zrodlo') or {}, w.get('modul') or {}
    t = []
    t.append('1. ŹRÓDŁO -> WP')
    if z.get('tekst'):
        t.append(z['tekst'])
    else:
        t.append(('BŁĄD: ' + z.get('blad', 'brak odpowiedzi')) if z else 'nie wykonano')
    t.append('')
    t.append('2. WP -> MODUŁ')
    if not m:
        t.append('nie wykonano')
    elif not m.get('ok'):
        t.append('BŁĄD: ' + str(m.get('blad') or 'pobieranie z WP nie powiodło się'))
    else:
        r = m.get('raport') or {}
        l = (r.get('liczniki') or {}).get('mecze') or {}
        t.append(f'Mecze w module: dodano {l.get("dodano", 0)}, zaktualizowano {l.get("zaktualizowano", 0)}, bez zmian {l.get("bez_zmian", 0)}, pominięto {l.get("pominieto", 0)}.')
        for p in (r.get('pominiete') or [])[:20]:
            t.append(f'  pominięty: {p}')
        for p in (r.get('zmiany') or [])[:30]:
            t.append(f'  zmiana: {p}')
        for p in (r.get('bledy') or [])[:10]:
            t.append(f'  BŁĄD: {p}')
        if m.get('zapisano') and r.get('kopia'):
            t.append(f'Kopia bazy przed zapisem: {r["kopia"]} ({m.get("kopia_kb", "?")} KB, {m.get("kopia_ms", "?")} ms)')
        if not m.get('zapisano'):
            t.append('Moduł już miał te dane (nic do zapisania).')
    t.append('')
    t.append(f'Czas: {w.get("czas_s", 0)} s.')
    return '\n'.join(t)
