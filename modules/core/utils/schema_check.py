"""Sprawdzenie wersji migracji bazy przy starcie modułu (E1).

Moduł nie powinien startować na bazie, która nie jest na aktualnej wersji migracji: zamiast serii wyjątków
("no such column ...") wypisujemy jeden czytelny komunikat z poleceniem i kończymy działanie.

Wersja wymagana = głowa (head) katalogu migracji modułu; wersja w bazie = tabela alembic_version.
Sprawdzenie dotyczy tylko uruchomień modułu (create_app z konfiguracją development/production); polecenia migracji
(`flask db ...`, `modules/migrate_db.py`) tworzą aplikację w innej konfiguracji i działają na starej bazie.
"""
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def resolve_db_url(db_url, instance_path):
    """Adres bazy z rozwiązaną ścieżką względną SQLite (Flask-SQLAlchemy liczy ją od katalogu instance aplikacji).

    Zwraca (url_do_silnika, sciezka_pliku_lub_None)."""
    url = make_url(db_url)
    if url.drivername.startswith('sqlite') and url.database and url.database != ':memory:':
        path = url.database
        if not os.path.isabs(path):
            path = os.path.join(instance_path, path)
        return 'sqlite:///' + Path(path).as_posix(), path
    return db_url, None


def schema_status(db_url, instance_path, migrations_dir):
    """Zwraca słownik: state (ok / outdated / ahead / unversioned / empty / missing), db_path, current, heads."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option('script_location', str(migrations_dir))
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    engine_url, path = resolve_db_url(db_url, instance_path)
    info = {'db_path': path or engine_url, 'heads': heads, 'current': []}
    if path is not None and not os.path.exists(path):
        info['state'] = 'missing'
        return info
    engine = create_engine(engine_url)
    try:
        tables = set(inspect(engine).get_table_names())
        if not tables:
            info['state'] = 'empty'
        elif 'alembic_version' not in tables:
            info['state'] = 'unversioned'
        else:
            with engine.connect() as conn:
                info['current'] = [r[0] for r in conn.execute(text('select version_num from alembic_version'))]
            known = {rev.revision for rev in script.walk_revisions()}
            if set(info['current']) == set(heads):
                info['state'] = 'ok'
            elif any(c not in known for c in info['current']):
                info['state'] = 'ahead'
            else:
                info['state'] = 'outdated'
    finally:
        engine.dispose()
    return info


def migrate_command(module_name):
    """Polecenie do wykonania (z folderu głównego projektu), z bezwzględną ścieżką do interpretera i skryptu."""
    script = Path(__file__).resolve().parents[2] / 'migrate_db.py'
    return f'"{sys.executable}" "{script}" {module_name}'


def migrate_commands(module_name):
    """Polecenie migracji w dwóch postaciach: PowerShell (wymaga operatora wywołania '&' przy cudzysłowie na początku wiersza) i cmd."""
    plain = migrate_command(module_name)
    return f'& {plain}', plain


def build_message(module_name, info):
    cur = ', '.join(info['current']) if info['current'] else 'brak'
    need = ', '.join(info['heads'])
    line = '=' * 72
    ps_cmd, cmd_cmd = migrate_commands(module_name)
    cmd = f'PowerShell:  {ps_cmd}\n    cmd:         {cmd_cmd}'
    env_hint = ''
    if os.environ.get('DATABASE_URL'):
        url = os.environ['DATABASE_URL']
        env_hint = ('\n    Zmienna DATABASE_URL musi być ustawiona tak samo w tym oknie, przed poleceniem:\n'
                    f'    PowerShell:  $env:DATABASE_URL = "{url}"\n'
                    f'    cmd:         set DATABASE_URL={url}')
    why = {
        'outdated': 'baza jest na starszej wersji migracji niż wymaga kod modułu',
        'ahead': 'baza ma wersję migracji, której ten kod nie zna (baza jest nowsza niż kod)',
        'unversioned': 'baza ma tabele, ale nie ma informacji o wersji migracji (tabela alembic_version)',
        'empty': 'baza jest pusta (brak tabel)',
        'missing': 'plik bazy nie istnieje',
    }[info['state']]
    if info['state'] == 'ahead':
        todo = '  Uruchom nowszą wersję kodu albo użyj bazy zgodnej z tym kodem; migrator tej bazy nie cofa.'
    elif info['state'] in ('empty', 'missing'):
        todo = ('  Utwórz bazę poleceniem db_init.py w folderze modułu albo wskaż istniejącą bazę zmienną DATABASE_URL.\n'
                f'  Potem, jeśli trzeba, zmigruj ją:\n    {cmd}')
    elif info['state'] == 'unversioned':
        todo = '  Nie zgaduję wersji bazy. Napisz do mnie, jak ją oznaczyć (stamp), albo użyj bazy zmigrowanej wcześniej.'
    else:
        todo = (f'  Wykonaj z folderu głównego projektu (skrypt sam zrobi kopię zapasową bazy obok pliku):\n    {cmd}{env_hint}\n'
                '  Potem uruchom moduł ponownie.')
    return (f'\n{line}\nBŁĄD: moduł {module_name} NIE został uruchomiony — {why}.\n'
            f'  Baza:             {info["db_path"]}\n'
            f'  Wersja w bazie:   {cur}\n'
            f'  Wersja wymagana:  {need}\n{todo}\n{line}\n')


def ensure_schema_current(app, migrations_dir):
    """Wywołać przy starcie modułu. Przy niezgodności wypisuje jeden komunikat i kończy proces (kod 1)."""
    info = schema_status(app.config['SQLALCHEMY_DATABASE_URI'], app.instance_path, migrations_dir)
    if info['state'] != 'ok':
        print(build_message(app.config.get('MODULE_NAME', 'moduł'), info), flush=True)
        sys.exit(1)
