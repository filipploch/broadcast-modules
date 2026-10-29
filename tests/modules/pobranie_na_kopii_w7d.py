"""W7d: pobranie pary z prawdziwego WP do WSKAZANEJ bazy (kopii), wypisuje raport jako JSON. Nie używać na bazie roboczej bez zgody właściciela.

    python tests/modules/pobranie_na_kopii_w7d.py <moduł> <plik bazy> <fragment nazwy ligi> <0|1: apply>
Wymaga działającego WP modułu (jedna instancja naraz) i wp-local\\dane-api-<id>.json."""
import json
import os
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
module, db_path, frag, apply = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3].lower(), sys.argv[4] == '1'
os.environ['BM_TEST_DATABASE_URL'] = 'sqlite:///' + db_path.as_posix()
sys.path[:0] = [str(REPO / 'modules' / module), str(REPO / 'modules')]
os.chdir(REPO / 'modules' / module)
from app import create_app  # noqa: E402

app = create_app('testing')
with app.app_context():
    from core.extensions import db
    from core.managers.wp_client import WpClient, fetch_competitions, load_wp_config
    from core.managers.wp_pull import pobierz_pare
    klient = WpClient(load_wp_config(app.config['MODULE_DIR']), timeout=60)
    i = next(x for x in fetch_competitions(klient)['items'] if frag in x['league_name'].lower())
    kopie = pathlib.Path(tempfile.mkdtemp(prefix='bm-w7d-kopie-'))          # kopie bazy z tej próby idą do katalogu tymczasowego, nie do instance
    w = pobierz_pare(klient, db, i['league_id'], i['season_id'], REPO / 'modules' / 'static' / 'images' / 'logos', module, kopie, apply)
    r = w.get('raport') or {}
    print(json.dumps({'ok': w['ok'], 'zapisano': w.get('zapisano'), 'blad': w.get('blad'), 'zmieniono': r.get('zmieniono'),
                      'liczniki': r.get('liczniki'), 'pominiete': r.get('pominiete'), 'korekty': r.get('korekty'), 'zwolnieni': r.get('zwolnieni')},
                     ensure_ascii=False))
