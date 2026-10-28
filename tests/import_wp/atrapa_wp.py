"""Atrapa REST WordPressa/SportsPressa dla testów importerów: kolekcje, tworzenie i aktualizacja rekordów z polami meta,
trasa czyszczenia meczu (bm/v1/event/<id>/clear). Zapisuje każde zapytanie, żeby testy mogły sprawdzać, co poszło do WP."""
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KOLEKCJE = ('leagues', 'seasons', 'teams', 'players', 'events')


class AtrapaWp:
    def __init__(self):
        self.dane = {k: {} for k in KOLEKCJE}          # kolekcja -> {id: obiekt}
        self.nastepne_id = 1000
        self.zapytania = []                             # (metoda, trasa, body)
        self.blad_dla = None                            # callable(kolekcja, body) -> True => odpowiedź 500
        self.wyczyszczone = []
        atrapa = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _odp(self, kod, body, naglowki=None):
                raw = json.dumps(body).encode()
                self.send_response(kod)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                for k, v in (naglowki or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

            def _obsluz(self, metoda):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                trasa = (q.get('rest_route') or [''])[0].strip('/')
                dlugosc = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(dlugosc).decode()) if dlugosc else None
                atrapa.zapytania.append((metoda, trasa, body))
                kod, odp, nag = atrapa.obsluz(metoda, trasa, body, {k: v[0] for k, v in q.items()})
                self._odp(kod, odp, nag)

            def do_GET(self):
                self._obsluz('GET')

            def do_POST(self):
                self._obsluz('POST')

        self.serwer = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.serwer.server_address[1]
        threading.Thread(target=self.serwer.serve_forever, daemon=True).start()

    def zamknij(self):
        self.serwer.shutdown()
        self.serwer.server_close()

    # -- logika REST
    def obsluz(self, metoda, trasa, body, params):
        m = re.fullmatch(r'bm/v1/event/(\d+)/clear', trasa)
        if m and metoda == 'POST':
            ev = self.dane['events'].get(int(m.group(1)))
            if ev is None:
                return 404, {'code': 'bm_not_event'}, {}
            for k in ('players', 'performance', 'results'):
                ev.pop(k, None)
            self.wyczyszczone.append(int(m.group(1)))
            return 200, {'cleared': int(m.group(1))}, {}
        m = re.fullmatch(r'sportspress/v2/(\w+)(?:/(\d+))?', trasa)
        if not m or m.group(1) not in KOLEKCJE:
            return 404, {'code': 'rest_no_route'}, {}
        kol, rid = m.group(1), m.group(2)
        if metoda == 'GET' and rid is None:
            per, strona = int(params.get('per_page', 10)), int(params.get('page', 1))
            wszystkie = sorted(self.dane[kol].values(), key=lambda o: o['id'])
            stron = max(1, -(-len(wszystkie) // per))
            return 200, wszystkie[(strona - 1) * per: strona * per], {'X-WP-TotalPages': str(stron), 'X-WP-Total': str(len(wszystkie))}
        if metoda == 'POST':
            if self.blad_dla and self.blad_dla(kol, body):
                return 500, {'message': 'Błąd wymuszony w teście'}, {}
            if rid is None:
                self.nastepne_id += 1
                obj = {'id': self.nastepne_id, 'meta': {}}
                self.dane[kol][obj['id']] = obj
            else:
                obj = self.dane[kol].get(int(rid))
                if obj is None:
                    return 404, {'code': 'rest_post_invalid_id'}, {}
            for k, v in (body or {}).items():
                if k == 'meta':
                    obj['meta'].update(v)
                else:
                    obj[k] = v
            if kol == 'players' and ('current_teams' in (body or {}) or 'past_teams' in (body or {})):
                # SportsPress sam składa wspólną listę 'teams' z drużyn aktualnych i dawnych (potwierdzone próbą na prawdziwym WP)
                obj['teams'] = list(dict.fromkeys([*obj.get('current_teams', []), *obj.get('past_teams', [])]))
            return (201 if rid is None else 200), obj, {}
        return 405, {}, {}

    # -- pomoce testowe
    def posty(self):
        return [z for z in self.zapytania if z[0] == 'POST' and not z[1].startswith('bm/')]

    def wyzeruj_zapytania(self):
        self.zapytania.clear()
        self.wyczyszczone.clear()

    def po_zrodle(self, kol, src_id):
        for o in self.dane[kol].values():
            if (o.get('meta') or {}).get('bm_source_id') == str(src_id):
                return o
        return None
