"""E2a: logi modułu do pliku (core/utils/logs.py): folder uruchomienia, nazwa pliku, format z ms, pominięcie wierszy HTTP,
limit rozmiaru, restart w tym samym folderze, czyszczenie całych folderów po 30 dniach."""
import logging
import os
import re
import shutil
import tempfile
import time
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path

import harness

APP, TMP = harness.boot("futsal_nalf")

LINE_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \[(INFO|ERROR|WARNING)\] ")


class LogiModulu(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(tempfile.mkdtemp(prefix="bm-logs-"))
        os.environ["BM_LOGS_DIR"] = str(self.root_dir)
        os.environ.pop("BM_LOG_RUN_DIR", None)
        self.root = logging.getLogger()
        self.old_level = self.root.level

    def tearDown(self):
        for h in list(self.root.handlers):
            if getattr(h, "_bm_file", False):
                h.close()
                self.root.removeHandler(h)
        self.root.setLevel(self.old_level)
        os.environ.pop("BM_LOGS_DIR", None)
        os.environ.pop("BM_LOG_RUN_DIR", None)
        shutil.rmtree(self.root_dir, ignore_errors=True)

    def _handler(self):
        return next(h for h in self.root.handlers if getattr(h, "_bm_file", False))

    def _detach(self):
        h = self._handler()
        h.close()
        self.root.removeHandler(h)

    def test_tryb_testowy_nie_tworzy_pliku(self):
        from core.utils.logs import setup_file_logging
        self.assertIsNone(setup_file_logging("futsal_nalf", testing=True))
        self.assertEqual(list(self.root_dir.iterdir()), [])

    def test_wlasny_folder_uruchomienia_gdy_modul_startuje_osobno(self):
        from core.utils.logs import setup_file_logging, MAX_BYTES
        path = setup_file_logging("futsal_nalf")
        self.assertEqual(path.name, "modul-futsal_nalf.log")
        self.assertEqual(path.parent.parent, self.root_dir)
        self.assertRegex(path.parent.name, r"^logs-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$")
        h = self._handler()
        self.assertIsInstance(h, RotatingFileHandler)
        self.assertEqual(h.maxBytes, MAX_BYTES)

    def test_folder_zalozony_przez_hub_jest_uzyty(self):
        from core.utils.logs import setup_file_logging
        hub_dir = self.root_dir / "logs-2026-10-08-12-00-00"
        os.environ["BM_LOG_RUN_DIR"] = str(hub_dir)
        path = setup_file_logging("futsal_nalf")
        self.assertEqual(path, hub_dir / "modul-futsal_nalf.log")
        self.assertEqual([p.name for p in self.root_dir.iterdir()], ["logs-2026-10-08-12-00-00"])

    def test_wiersze_maja_znacznik_z_milisekundami_a_http_werkzeug_nie_trafia_do_pliku(self):
        from core.utils.logs import setup_file_logging
        path = setup_file_logging("futsal_nalf")
        logging.getLogger("werkzeug").warning("127.0.0.1 GET /ui 200")
        logging.getLogger("app.test").error("wazny blad")
        self._handler().flush()
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("GET /ui", text)
        lines = [l for l in text.splitlines() if l]
        self.assertTrue(lines and all(LINE_FORMAT.match(l) for l in lines), lines)
        self.assertTrue(any("wazny blad" in l for l in lines))

    def test_restart_modulu_w_tym_samym_folderze_dopisuje_z_separatorem(self):
        from core.utils.logs import setup_file_logging
        hub_dir = self.root_dir / "logs-2026-10-08-12-00-00"
        os.environ["BM_LOG_RUN_DIR"] = str(hub_dir)
        path = setup_file_logging("futsal_nalf")
        logging.getLogger("app.test").error("przed awaria")
        self._detach()
        self.assertEqual(setup_file_logging("futsal_nalf"), path)             # drugi start = ten sam plik
        logging.getLogger("app.test").error("po restarcie")
        self._handler().flush()
        text = path.read_text(encoding="utf-8")
        i1, i2, i3 = text.index("przed awaria"), text.index("ponowne uruchomienie składnika modul-futsal_nalf"), text.index("po restarcie")
        self.assertTrue(i1 < i2 < i3, text)

    def test_poziom_konsoli_zostaje_a_plik_dostaje_info(self):
        from core.utils.logs import setup_file_logging
        self.root.setLevel(logging.ERROR)
        console = logging.StreamHandler()
        self.root.addHandler(console)
        try:
            path = setup_file_logging("futsal_nalf")
            self.assertEqual(console.level, logging.ERROR)
            logging.getLogger("app.test").info("info do pliku")
            self._handler().flush()
            self.assertIn("info do pliku", path.read_text(encoding="utf-8"))
        finally:
            self.root.removeHandler(console)

    def test_czyszczenie_usuwa_cale_stare_foldery_a_zostawia_swieze_i_obce(self):
        from core.utils.logs import remove_old_run_dirs
        old = self.root_dir / "logs-2026-01-01-10-00-00"
        fresh = self.root_dir / "logs-2026-10-01-10-00-00"
        other = self.root_dir / "inny"
        for d in (old, fresh, other):
            d.mkdir()
            (d / "hub.log").write_text("x")
        t = time.time() - 31 * 86400
        for p in (old / "hub.log", old, other / "hub.log", other):
            os.utime(p, (t, t))
        self.assertEqual(remove_old_run_dirs(self.root_dir), 1)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists() and other.exists())


if __name__ == "__main__":
    unittest.main()
