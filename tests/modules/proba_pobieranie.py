"""Próba pobierania z prawdziwego WP (W7a) na KOPII bazy modułu (nie dotyka modules/<moduł>/instance/database.db).

    python tests/modules/proba_pobieranie.py <futsal_nalf|garbarnia> [liga:sezon ...] [--zapis]

Wymaga działającej instancji WP modułu (wp-nalf.bat / wp-garbarnia.bat) i wp-local\\dane-api-<id>.json. Bez par w poleceniu bierze wszystkie z listy WP.
Domyślnie sam podgląd na kopii; --zapis zapisuje do kopii, potem powtarza pobranie (kontrola powtarzalności). Kopia: <katalog tymczasowy>/proba-<moduł>.db."""
import json
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    zapis = '--zapis' in sys.argv
    module = args[0] if args else 'futsal_nalf'
    pary = args[1:]
    src = REPO / 'modules' / module / 'instance' / 'database.db'
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=f'bm-proba-{module}-'))
    dst = tmp / 'database.db'
    shutil.copy(src, dst)
    os.environ['BM_TEST_DATABASE_URL'] = 'sqlite:///' + dst.as_posix()
    sys.path[:0] = [str(REPO / 'modules' / module), str(REPO / 'modules')]
    os.chdir(REPO / 'modules' / module)
    from app import create_app
    app = create_app('testing')
    with app.app_context():
        from core.extensions import db
        from core.managers.wp_client import WpClient, fetch_competitions, load_wp_config
        from core.managers.wp_pull import pobierz_pare
        cfg = load_wp_config(app.config['MODULE_DIR'])
        klient = WpClient(cfg, timeout=60)
        lista = fetch_competitions(klient)['items']
        if pary:
            lista = [i for i in lista if i['key'] in pary]
        logo_root = REPO / 'modules' / 'static' / 'images' / 'logos'
        print(f'Kopia bazy: {dst}')
        for i in lista:
            for tryb in (['podgląd', 'zapis', 'powtórka'] if zapis else ['podgląd']):
                w = pobierz_pare(klient, db, i['league_id'], i['season_id'], logo_root, module, tmp / 'kopie-wp', tryb == 'zapis')
                if tryb == 'powtórka':
                    w = pobierz_pare(klient, db, i['league_id'], i['season_id'], logo_root, module, tmp / 'kopie-wp', True)
                print(f'\n=== {i["league_name"]} — {i["season_name"]} [{tryb}] ===')
                if not w['ok']:
                    print('BŁĄD:', w['blad'])
                    continue
                r = w['raport']
                print('zapisano:', w['zapisano'], '| liczniki:', json.dumps(r['liczniki'], ensure_ascii=False))
                for k in ('pominiete', 'korekty', 'rozbieznosci', 'brak_logo', 'skroty_wyliczone', 'dolaczono', 'nieobecne', 'zablokowane'):
                    if r[k]:
                        print(f'  {k} ({len(r[k])}):', '; '.join(r[k][:8]))
                print('  do ustalenia:', r['do_ustalenia_liczba'])
                if tryb == 'powtórka':
                    print('  powtórka zmieniono:', r['zmieniono'])
        if zapis:
            from core.models.base_game import get_game_model
            from core.models.base_player import get_player_model
            from core.models.base_team import get_team_model
            print('\nW kopii: drużyn', get_team_model().query.count(), '| zawodników', get_player_model().query.count(), '| meczów', get_game_model().query.count())


if __name__ == '__main__':
    main()
