"""E2a: logi modułu do pliku (core/utils/logs.py): nazwa i położenie, pominięcie wierszy HTTP, limit rozmiaru, czyszczenie po 30 dniach."""
import logging
import os
import tempfile
import time
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path

import harness

APP, TMP = harness.boot("futsal_nalf")


class LogiModulu(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="bm-logs-"))
        os.environ["BM_LOGS_DIR"] = str(self.dir)
        self.root = logging.getLogger()
        self.old_level, self.old_handlers = self.root.level, list(self.root.handlers)

    def tearDown(self):
        for h in list(self.root.handlers):
            if getattr(h, "_bm_file", False):
                h.close()
                self.root.removeHandler(h)
        self.root.setLevel(self.old_level)
        os.environ.pop("BM_LOGS_DIR", None)

    def _handler(self):
        return next(h for h in self.root.handlers if getattr(h, "_bm_file", False))

    def test_tryb_testowy_nie_tworzy_pliku(self):
        from core.utils.logs import setup_file_logging
        self.assertIsNone(setup_file_logging("futsal_nalf", testing=True))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_plik_ma_nazwe_z_data_w_wskazanym_folderze_i_limit_rozmiaru(self):
        from core.utils.logs import setup_file_logging, MAX_BYTES
        path = setup_file_logging("futsal_nalf")
        self.assertEqual(path.parent, self.dir)
        self.assertRegex(path.name, r"^modul-futsal_nalf-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log$")
        h = self._handler()
        self.assertIsInstance(h, RotatingFileHandler)
        self.assertEqual(h.maxBytes, MAX_BYTES)

    def test_wiersze_http_werkzeug_nie_trafiaja_do_pliku_a_inne_tak(self):
        from core.utils.logs import setup_file_logging
        path = setup_file_logging("futsal_nalf")
        logging.getLogger("werkzeug").warning("127.0.0.1 GET /ui 200")
        logging.getLogger("app.test").error("wazny blad")
        self._handler().flush()
        text = path.read_text(encoding="utf-8")
        self.assertIn("wazny blad", text)
        self.assertNotIn("GET /ui", text)

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

    def test_czyszczenie_usuwa_tylko_stare_logi(self):
        from core.utils.logs import remove_old_logs
        old, new, other = self.dir / "hub-a.log", self.dir / "modul-b.log.1", self.dir / "notatka.txt"
        for p in (old, new, other):
            p.write_text("x")
        t = time.time() - 31 * 86400
        os.utime(old, (t, t)); os.utime(other, (t, t))
        self.assertEqual(remove_old_logs(self.dir), 1)
        self.assertFalse(old.exists()); self.assertTrue(new.exists()); self.assertTrue(other.exists())


if __name__ == "__main__":
    unittest.main()
