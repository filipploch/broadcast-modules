"""Panel bez otwartej sesji (stan zwykly po E1, np. zaraz po starcie modulu): zadne zdarzenie Socket.IO ani strona nie moze
konczyc sie wyjatkiem. Wspolne dla obu modulow; kazdy modul ma wlasny plik test_bez_sesji.py, ktory wola make(APP)."""
import re
import unittest

# Zdarzenia pomijane celowo: powoduja skutki poza procesem (pakiet Wake-on-LAN, eksport plikow w watku w tle) albo sa zdarzeniami biblioteki.
POMIJANE = {'connect', 'disconnect', 'wake_recorder_plugin', 'replay_export_run'}
# Zdarzenia, ktore bez danych koncza sie bledem klienta (brak wymaganego pola), a nie brakiem sesji: podajemy minimalny ladunek.
LADUNKI = {'trigger_sequence': {'sequence': 'halftime_start'}}


def make(APP):
    import harness

    class BezSesji(unittest.TestCase):
        def setUp(self):
            harness.reset_db(APP)

        def test_zadne_zdarzenie_socketio_nie_rzuca_wyjatku(self):
            from core.extensions import socketio
            bledy = []
            zdarzenia = sorted(socketio.server.handlers['/'])
            self.assertGreater(len(zdarzenia), 50)             # zabezpieczenie: lista zdarzen nie moze byc pusta
            for ev in zdarzenia:
                if ev in POMIJANE:
                    continue
                client = socketio.test_client(APP)
                try:
                    wywolania = [(LADUNKI[ev],)] if ev in LADUNKI else [(), ({},)]
                    for args in wywolania:
                        try:
                            client.emit(ev, *args)
                            break
                        except TypeError as e:
                            if 'positional argument' in str(e) and not args:
                                continue                      # handler wymaga argumentu: ponawiamy z pustym ladunkiem
                            bledy.append(f'{ev}: {type(e).__name__}: {e}')
                            break
                        except Exception as e:
                            bledy.append(f'{ev}: {type(e).__name__}: {e}')
                            break
                finally:
                    client.disconnect()
            self.assertEqual(bledy, [], 'zdarzenia rzucajace wyjatek bez otwartej sesji:\n' + '\n'.join(bledy))

        def test_zadna_strona_get_nie_rzuca_wyjatku_ani_500(self):
            client = APP.test_client()
            bledy = []
            sprawdzone = 0
            for rule in APP.url_map.iter_rules():
                if 'GET' not in rule.methods or rule.rule.startswith('/static'):
                    continue
                if 'scrape' in rule.rule and not rule.rule.endswith('/status'):
                    continue                                  # pobieranie danych z internetu
                url = re.sub(r'<(?:int:)?\w+>', '1', rule.rule)
                url = url.replace('<path:filename>', 'x').replace('<content_type>', 'players')
                sprawdzone += 1
                try:
                    r = client.get(url)
                    if r.status_code >= 500:
                        bledy.append(f'{url}: HTTP {r.status_code}')
                except Exception as e:
                    bledy.append(f'{url}: {type(e).__name__}: {e}')
            self.assertGreater(sprawdzone, 50)
            self.assertEqual(bledy, [], 'strony rzucajace wyjatek bez otwartej sesji:\n' + '\n'.join(bledy))

    return BezSesji
