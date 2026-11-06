"""Pomiar czasów odpowiedzi WP w trakcie meczu (generalna, wpis G-OBC): tylko ODCZYT (GET), jedno żądanie co kilka sekund, nic nie zapisuje w WP.

    python tests/modules/pomiar_wp.py 8091 [--liczba 120] [--co 3] [--liga 820 --sezon 819]
    python tests/modules/pomiar_wp.py 8092 ...

Mierzy: (1) lekki odczyt (lista ligi, 1 element), (2) tabela oficjalna (bm/v1/table?mode=final), (3) tabela wirtualna (mode=live) dla podanej ligi i sezonu (id termów w WP; bez nich tylko (1)).
Wynik: wiersze na ekranie i plik CSV w wp-local\\generalna\\pomiar-<port>-<czas>.csv, na końcu podsumowanie (mediana, 95. percentyl, maksimum, liczba błędów). Przerwanie: Ctrl+C
(podsumowanie i tak się wypisze). Dane logowania z wp-local\\dane-api-<nalf|garbarnia>.json (8091 = nalf, 8092 = garbarnia)."""
import argparse
import base64
import csv
import json
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parents[2]
WPL = REPO / 'wp-local'
MODUL = {8091: 'nalf', 8092: 'garbarnia', 8099: 'nalf'}      # 8099: instancja próbna (kopia bazy)


def zadanie(port, trasa, auth, timeout=30):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/index.php?rest_route=/{trasa}', headers={'Authorization': auth, 'Accept': 'application/json'})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            kod = r.status
    except urllib.error.HTTPError as e:
        kod = e.code
    except Exception:
        kod = 0
    return kod, (time.perf_counter() - t0) * 1000


def percentyl(lista, p):
    if not lista:
        return float('nan')
    s = sorted(lista)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def podsumuj(wyniki):
    """wyniki: {nazwa: [(kod, ms), ...]} -> wiersze tekstu z medianą, p95, maksimum i błędami (kod różny od 200)."""
    w = []
    for nazwa, lista in wyniki.items():
        ok = [ms for kod, ms in lista if kod == 200]
        bledy = sum(1 for kod, _ in lista if kod != 200)
        w.append(f'{nazwa}: żądań {len(lista)}, błędów {bledy}, mediana {statistics.median(ok):.0f} ms, p95 {percentyl(ok, 95):.0f} ms, max {max(ok):.0f} ms' if ok else f'{nazwa}: żądań {len(lista)}, błędów {bledy}, brak udanych odpowiedzi')
    return w


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('port', type=int, choices=sorted(MODUL))
    ap.add_argument('--liczba', type=int, default=120)
    ap.add_argument('--co', type=float, default=3.0, help='odstęp między seriami w sekundach (minimum 1)')
    ap.add_argument('--liga', type=int)
    ap.add_argument('--sezon', type=int)
    a = ap.parse_args(argv)
    creds = json.loads((WPL / f'dane-api-{MODUL[a.port]}.json').read_text(encoding='utf-8-sig'))
    auth = 'Basic ' + base64.b64encode(f"{creds['user']}:{creds['password']}".encode()).decode()
    zestaw = {'lekki odczyt (lista ligi)': 'sportspress/v2/leagues&per_page=1&_fields=id'}
    if a.liga and a.sezon:
        zestaw['tabela oficjalna (final)'] = f'bm/v1/table&league={a.liga}&season={a.sezon}&mode=final'
        zestaw['tabela wirtualna (live)'] = f'bm/v1/table&league={a.liga}&season={a.sezon}&mode=live'
    katalog = WPL / 'generalna'
    katalog.mkdir(parents=True, exist_ok=True)
    plik = katalog / f'pomiar-{a.port}-{datetime.now():%Y%m%d-%H%M%S}.csv'
    wyniki = {n: [] for n in zestaw}
    with plik.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['czas', 'pomiar', 'kod', 'ms'])
        try:
            for i in range(a.liczba):
                for nazwa, trasa in zestaw.items():
                    kod, ms = zadanie(a.port, trasa, auth)
                    wyniki[nazwa].append((kod, ms))
                    w.writerow([datetime.now().strftime('%H:%M:%S'), nazwa, kod, round(ms)])
                    f.flush()
                    print(f'{datetime.now():%H:%M:%S} {nazwa}: HTTP {kod}, {ms:.0f} ms', flush=True)
                time.sleep(max(1.0, a.co))
        except KeyboardInterrupt:
            print('Przerwano.')
    print('\nPODSUMOWANIE (' + str(plik) + '):')
    for linia in podsumuj({n: l for n, l in wyniki.items() if l}):
        print('  ' + linia)
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
