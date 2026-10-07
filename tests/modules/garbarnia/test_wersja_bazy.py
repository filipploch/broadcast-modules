"""E1: sprawdzenie wersji migracji bazy przy starcie modulu. Baza niezgodna z kodem = jeden czytelny komunikat z poleceniem
i brak uruchomienia (zamiast serii wyjatkow 'no such column'). Polecenia migracji dzialaja na starej bazie."""
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import harness

APP, TMP = harness.boot("garbarnia")
MODULE = "garbarnia"
ENTRY = "garbarnia.py"
OLD_REVISION = "2d7f9a3c6b1e"          # starsza, istniejaca wersja migracji tego modulu
REPO = pathlib.Path(__file__).resolve().parents[3]
MODULE_DIR = REPO / "modules" / MODULE


def _status(db_file):
    from core.utils.schema_check import schema_status
    return schema_status("sqlite:///" + pathlib.Path(db_file).as_posix(), str(MODULE_DIR / "instance"), MODULE_DIR / "migrations")


def _real_db():
    """Plik bazy aplikacji testowej (wszystkie moduly testowe w jednym procesie wspoldziela baze pierwszego z nich)."""
    return pathlib.Path(APP.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "", 1))


def _head():
    return _status(_real_db())["heads"][0]


class StanBazy(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="bm-schema-"))
        # baza z kompletem tabel (create_all w boot) — kopia, zeby zmieniac alembic_version
        self.db = self.dir / "baza.db"
        shutil.copy(_real_db(), self.db)

    def _set_version(self, revision):
        c = sqlite3.connect(self.db)
        c.execute("create table if not exists alembic_version (version_num varchar(32) not null)")
        c.execute("delete from alembic_version")
        if revision:
            c.execute("insert into alembic_version values (?)", (revision,))
        c.commit()
        c.close()

    def test_aktualna(self):
        self._set_version(_head())
        self.assertEqual(_status(self.db)["state"], "ok")

    def test_starsza_wersja(self):
        self._set_version(OLD_REVISION)
        st = _status(self.db)
        self.assertEqual((st["state"], st["current"]), ("outdated", [OLD_REVISION]))

    def test_baza_nowsza_niz_kod(self):
        self._set_version("ffffffffffff")
        self.assertEqual(_status(self.db)["state"], "ahead")

    def test_tabele_bez_wersji(self):
        c = sqlite3.connect(self.db)
        c.execute("drop table if exists alembic_version")
        c.commit()
        c.close()
        self.assertEqual(_status(self.db)["state"], "unversioned")

    def test_pusta_i_brakujaca(self):
        empty = self.dir / "pusta.db"
        sqlite3.connect(empty).close()
        self.assertEqual(_status(empty)["state"], "empty")
        self.assertEqual(_status(self.dir / "nie-ma.db")["state"], "missing")

    def test_komunikat_jest_jeden_i_zawiera_polecenie(self):
        from core.utils.schema_check import build_message
        self._set_version(OLD_REVISION)
        msg = build_message(MODULE, _status(self.db))
        self.assertEqual(msg.count("BŁĄD:"), 1)
        for needed in (MODULE, OLD_REVISION, _head(), "migrate_db.py", "uruchom moduł ponownie"):
            self.assertIn(needed, msg)


class UruchomienieModulu(unittest.TestCase):
    """Prawdziwy skrypt startowy modulu na bazie niezgodnej: ma sie nie uruchomic, wypisac jeden komunikat, bez wyjatkow."""

    def _run(self, *args, env_extra=None):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", **(env_extra or {})}
        return subprocess.run([sys.executable, *args], capture_output=True, text=True, encoding="utf-8", env=env,
                              cwd=REPO, timeout=120)

    def test_stara_baza_zatrzymuje_start_z_jednym_komunikatem(self):
        d = pathlib.Path(tempfile.mkdtemp(prefix="bm-schema-"))
        db = d / "stara.db"
        shutil.copy(_real_db(), db)
        c = sqlite3.connect(db)
        c.execute("create table alembic_version (version_num varchar(32) not null)")
        c.execute("insert into alembic_version values (?)", (OLD_REVISION,))
        c.commit()
        c.close()
        r = self._run(str(REPO / "modules" / ENTRY), env_extra={"DATABASE_URL": "sqlite:///" + db.as_posix()})
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out.count("BŁĄD:"), 1)
        self.assertIn("NIE został uruchomiony", out)
        self.assertIn("migrate_db.py", out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("no such column", out)


@unittest.skipUnless((MODULE_DIR / "instance" / "database.db").exists(), "brak lokalnej bazy modulu (instance/database.db)")
class SkryptMigracji(unittest.TestCase):
    def test_migracja_kopii_lokalnej_bazy_z_kopia_zapasowa(self):
        d = pathlib.Path(tempfile.mkdtemp(prefix="bm-migr-"))
        db = d / "kopia.db"
        shutil.copy(MODULE_DIR / "instance" / "database.db", db)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DATABASE_URL": "sqlite:///" + db.as_posix()}
        run = lambda: subprocess.run([sys.executable, str(REPO / "modules" / "migrate_db.py"), MODULE], capture_output=True,
                                     text=True, encoding="utf-8", env=env, cwd=REPO, timeout=300)
        was_current = _status(db)["state"] == "ok"
        r1 = run()
        self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        self.assertEqual(_status(db)["state"], "ok")
        backups = list(d.glob("kopia.db.bak_*"))
        self.assertEqual(len(backups), 0 if was_current else 1)        # kopia zapasowa tylko gdy cos zmieniano
        r2 = run()                                                      # drugi raz: nic do zrobienia, bez nowej kopii
        self.assertEqual(r2.returncode, 0)
        self.assertIn("aktualna", r2.stdout)
        self.assertEqual(len(list(d.glob("kopia.db.bak_*"))), len(backups))


if __name__ == "__main__":
    unittest.main()
