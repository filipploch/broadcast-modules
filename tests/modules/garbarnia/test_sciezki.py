"""E1: sciezki plikow modulu (SEQUENCES_PATH, REPLAY_EXPORT_DIR) liczone od polozenia plikow modulu, nie od biezacego folderu."""
import os
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock

import harness

APP, TMP = harness.boot("garbarnia")
MODULE = "garbarnia"
REPO = pathlib.Path(__file__).resolve().parents[3]
MODULE_DIR = REPO / "modules" / MODULE


class SciezkiModulu(unittest.TestCase):
    def setUp(self):
        import core.managers as cm
        self.cm = cm
        self.cwd = os.getcwd()
        self.ctx = APP.app_context()
        self.ctx.push()

    def tearDown(self):
        os.chdir(self.cwd)
        self.cm._sequence_manager = None
        self.cm._replay_export_manager = None
        self.cm._hub_client = None
        self.ctx.pop()

    def _cwds(self):
        return [REPO, REPO / "modules", MODULE_DIR, pathlib.Path(tempfile.mkdtemp(prefix="bm-cwd-"))]

    def test_sciezki_w_konfiguracji_sa_bezwzgledne_i_wskazuja_pliki_modulu(self):
        seq = pathlib.Path(APP.config["SEQUENCES_PATH"])
        self.assertTrue(seq.is_absolute())
        self.assertEqual(seq, MODULE_DIR / "app" / "sequences" / "sequences.py")
        self.assertTrue(seq.exists())
        data = pathlib.Path(APP.config["REPLAY_EXPORT_DIR"])
        self.assertTrue(data.is_absolute())
        self.assertEqual(data, MODULE_DIR / "app" / "data")

    def test_wczytanie_sekwencji_dziala_z_kazdego_folderu(self):
        for cwd in self._cwds():
            os.chdir(cwd)
            self.cm._sequence_manager = None
            self.cm._hub_client = MagicMock()
            sm = self.cm.get_sequence_manager()
            self.assertIn("halftime_start", sm.sequences, f"cwd={cwd}")
            self.assertIn("goal", sm.dynamic_sequences, f"cwd={cwd}")

    def test_uruchomienie_sekwencji_z_innego_folderu(self):
        os.chdir(tempfile.mkdtemp(prefix="bm-cwd-"))
        self.cm._hub_client = MagicMock()
        sm = self.cm.get_sequence_manager()
        sequence_id = sm.trigger("halftime_start")
        self.assertTrue(sequence_id.startswith("halftime_start_"))
        with self.assertRaises(ValueError):                                    # nieznana sekwencja nadal daje czytelny blad
            sm.trigger("nie-ma-takiej")

    def test_katalog_eksportu_powtorek_jest_bezwzgledny_niezaleznie_od_folderu(self):
        os.chdir(tempfile.mkdtemp(prefix="bm-cwd-"))
        self.cm._replay_export_manager = None
        mgr = self.cm.get_replay_export_manager()
        self.assertEqual(pathlib.Path(mgr.data_dir), MODULE_DIR / "app" / "data")


if __name__ == "__main__":
    unittest.main()
