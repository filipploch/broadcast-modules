"""Uruchamia testy jednego modulu:  python tests/modules/run.py [futsal_nalf|garbarnia]   (domyslnie futsal_nalf)"""
import pathlib, sys, unittest

module = sys.argv[1] if len(sys.argv) > 1 else "futsal_nalf"
here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here))
suite = unittest.defaultTestLoader.discover(str(here / module), top_level_dir=str(here / module))
res = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if res.wasSuccessful() else 1)
