"""Próba ręczna W8a: UDAWANE źródło Superscore z dwoma meczami „w toku”, do sprawdzenia importu stanu i wyniku na żywo na KOPII WP (port 8099).

    python tests/modules/proba_zrodlo_zywo.py <katalog pamięci podręcznej>

Pobiera prawdziwy terminarz sezonu (jedno zapytanie, tylko odczyt), wybiera dwa pierwsze mecze nierozpoczęte, ustawia je w pamięci podręcznej jako „w toku”:
mecz RÓWNOLEGŁY (1:0) i mecz TRANSMITOWANY (7:7). Zapisuje plik pod nazwą, pod jaką odczyta go odswiez.py z --cache. Wypisuje nazwy meczów.
Niczego nie zapisuje do WP ani do baz."""
import copy
import hashlib
import json
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'import_wp'))
import superscore  # noqa: E402

ZRODLA = json.loads((REPO / 'tools' / 'import_wp' / 'zrodla.json').read_text(encoding='utf-8'))


def przygotuj(katalog, terminarz=None):
    konf = ZRODLA['garbarnia']
    params = {'season-id': konf['sezon'], 'with-upcoming': 'yes'}
    fx = copy.deepcopy(terminarz) if terminarz is not None else superscore.SuperscoreApi().get(superscore.FIXTURES, **params)
    nierozpoczete = [e for e in fx['events'] if e.get('match_state') == 0 and e.get('team1') and e.get('team2')]
    nierozpoczete.sort(key=lambda e: (e.get('match_date') or {}).get('seconds', 0))
    if len(nierozpoczete) < 2:
        raise SystemExit('W terminarzu nie ma dwóch meczów nierozpoczętych.')
    nazwy = []
    for e, (g, a) in zip(nierozpoczete[:2], ((1, 0), (7, 7))):
        e['match_state'] = 1
        e['scores'] = [{'type': 0, 'team1': g, 'team2': a}]
        nazwy.append(f'{(e["team1"].get("name") or "?")} - {(e["team2"].get("name") or "?")}')
    pelny = superscore.FIXTURES + '?' + urllib.parse.urlencode(params)
    katalog = Path(katalog)
    katalog.mkdir(parents=True, exist_ok=True)
    (katalog / (hashlib.md5(pelny.encode()).hexdigest() + '.json')).write_text(json.dumps(fx, ensure_ascii=False), encoding='utf-8')
    return nazwy


if __name__ == '__main__':
    r, t = przygotuj(sys.argv[1])
    print(f'Mecz RÓWNOLEGŁY (w źródle "w toku" 1:0): {r}')
    print(f'Mecz do TRANSMISJI (w źródle "w toku" 7:7, wybierz go w panelu): {t}')
